"""Phase 3: Autonomous UI driving via chrome-devtools MCP.

Navigates a real product UI using AI agents, capturing screenshots, text
descriptions, AND a navigation action trace (Fix 2) for each target screen.
Captures are a pure function of (product, product_version, fixture_id, screen_id)
so they are safely reused across clean and all variants of the same page (L3/L7).

The infrastructure (bring-up, version probe, pre-auth, fixture) is a small
per-product adapter selected by the `product` argument (plan §2.2). Grafana is
fully implemented; Keycloak/NetBox bring-up is completed in their own stages.
The `product` argument is a prediction input, never a ground-truth label (L1).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from pipeline.claude_runner import parse_mcp_trace, run_claude, run_claude_stream
from pipeline.config import (
    CHROME_DEBUG_PORT,
    CHROME_EXE,
    CHROME_USER_DATA_DIR,
    DESCRIPTIONS_DIR,
    DOCKER_BIN,
    FIXTURES_DIR,
    MODEL_DRIVE,
    NAV_LOGS_DIR,
    PLANS_DIR,
    PROMPTS_DIR,
    SCREENSHOTS_DIR,
    TRACES_DIR,
    capture_subdir,
    ensure_dirs,
    spec,
)
from pipeline.config import CLAIMS_DIR
from pipeline.models import DriverPlan, NavigationStep, NavigationTrace, ScreenState

_MCP_TOOLS = "mcp__chrome-devtools__*,Write,Read"


# ---------------------------------------------------------------------------
# Infrastructure adapter (per-product bring-up + version probe), selected by
# `product`. Helpers are generic; Grafana aliases are kept at the bottom.
# ---------------------------------------------------------------------------

def wait_for_product(product: str = "grafana", timeout: int = 90) -> bool:
    """Poll the product's reachability endpoint until it responds OK."""
    s = spec(product)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = subprocess.run(
                ["curl", "-sf", s.health_url],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                print(f"{s.name} healthy at {s.url}")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        time.sleep(2)
    print(f"ERROR: {s.name} did not become healthy within {timeout}s")
    return False


def _compose_up(s) -> bool:
    compose = FIXTURES_DIR / s.name / (s.compose_file or "docker-compose.yml")
    if not compose.exists():
        print(f"ERROR: compose file not found: {compose}")
        return False
    result = subprocess.run(
        [DOCKER_BIN, "compose", "-f", str(compose), "up", "-d"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: compose up failed: {result.stderr.strip()}")
        return False
    print(f"Started {s.name} via docker compose ({compose})")
    return wait_for_product(s.name)


def start_product(product: str = "grafana") -> bool:
    """Bring the product up (docker run or docker compose) and wait for health."""
    s = spec(product)
    if s.bring_up == "compose":
        return _compose_up(s)

    subprocess.run([DOCKER_BIN, "rm", "-f", s.container], capture_output=True, text=True)
    cmd = [DOCKER_BIN, "run", "-d", "-p", f"{s.port}:{s.port}", "--name", s.container]
    for k, v in s.env:
        cmd += ["-e", f"{k}={v}"]
    cmd.append(s.image)
    cmd += list(s.run_args)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: Failed to start {s.name}: {result.stderr.strip()}")
        return False
    print(f"Started container {s.container} ({s.image})")
    return wait_for_product(product)


def stop_product(product: str = "grafana") -> None:
    """Stop and remove the product container(s)."""
    s = spec(product)
    if s.bring_up == "compose":
        compose = FIXTURES_DIR / s.name / (s.compose_file or "docker-compose.yml")
        if compose.exists():
            subprocess.run([DOCKER_BIN, "compose", "-f", str(compose), "down"],
                           capture_output=True, text=True)
            print(f"Stopped {s.name} compose stack")
        return
    subprocess.run([DOCKER_BIN, "rm", "-f", s.container], capture_output=True, text=True)
    print(f"Stopped and removed container {s.container}")


def _probe_json(url: str, key: str, timeout: int) -> str | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get(key)
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return None


def _keycloak_version(s, timeout: int) -> str | None:
    """admin token -> GET /admin/serverinfo -> systemInfo.version; fallback to tag."""
    try:
        token_url = f"{s.url}/realms/master/protocol/openid-connect/token"
        body = urllib.parse.urlencode({
            "grant_type": "password", "client_id": "admin-cli",
            "username": s.user, "password": s.password,
        }).encode("utf-8")
        req = urllib.request.Request(token_url, data=body, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            token = json.loads(resp.read().decode("utf-8")).get("access_token")
        info_req = urllib.request.Request(
            f"{s.url}/admin/serverinfo", headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(info_req, timeout=timeout) as resp:
            info = json.loads(resp.read().decode("utf-8"))
            return (info.get("systemInfo") or {}).get("version")
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError, KeyError):
        return s.image_tag  # documented fallback (plan §2.2)


def get_product_version(product: str = "grafana", timeout: int = 5) -> str | None:
    """Read the running product's reported version via its version probe."""
    s = spec(product)
    if s.version_probe == "grafana_health":
        return _probe_json(s.health_url, "version", timeout)
    if s.version_probe == "netbox_status":
        return _probe_json(f"{s.url}/api/status/", "netbox-version", timeout)
    if s.version_probe == "keycloak_serverinfo":
        return _keycloak_version(s, timeout)
    return None


def assert_version(product: str = "grafana") -> bool:
    """Enforce the deployed==labeled invariant (Fix 1), generalized per product.

    Returns False only on a *confirmed* mismatch — running on the wrong version
    silently produces meaningless verdicts, so we refuse rather than proceed. If
    the version can't be read (product not up yet), we warn and let the caller
    decide; the agent calls would fail naturally anyway.
    """
    s = spec(product)
    expected = s.version
    actual = get_product_version(product)
    if actual is None:
        print(f"WARNING: could not read {s.name} version; cannot confirm "
              f"deployed == {expected}.")
        return True
    if actual != expected:
        print(f"ERROR: version mismatch — deployed {s.name} {actual!r} != labeled "
              f"{expected!r}. Refusing to run: the ground truth was labeled against "
              f"{expected}, so verdicts here would be meaningless. Pin the image to "
              f"{s.image.rsplit(':', 1)[0]}:{expected} and redeploy.")
        return False
    print(f"Version preflight OK: deployed {s.name} {actual} == labeled {expected}")
    return True


# ---------------------------------------------------------------------------
# Chrome CDP management
# ---------------------------------------------------------------------------

def check_chrome_cdp(timeout: int = 3) -> bool:
    """Return True if Chrome CDP is already listening on CHROME_DEBUG_PORT."""
    url = f"http://localhost:{CHROME_DEBUG_PORT}/json/version"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def start_chrome() -> bool:
    """Launch Chrome with remote debugging if CDP is not already available."""
    if check_chrome_cdp():
        print(f"Chrome CDP already accessible on port {CHROME_DEBUG_PORT}")
        return True

    print(f"Starting Chrome with --remote-debugging-port={CHROME_DEBUG_PORT} ...")
    try:
        subprocess.Popen(
            [
                CHROME_EXE,
                f"--remote-debugging-port={CHROME_DEBUG_PORT}",
                f"--user-data-dir={CHROME_USER_DATA_DIR}",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        print(f"ERROR: Chrome not found at {CHROME_EXE!r}. Start Chrome manually with:")
        print(f"  chrome --remote-debugging-port={CHROME_DEBUG_PORT}")
        return False

    deadline = time.time() + 15
    while time.time() < deadline:
        if check_chrome_cdp():
            print(f"Chrome CDP ready on port {CHROME_DEBUG_PORT}")
            return True
        time.sleep(1)

    print(f"ERROR: Chrome CDP did not become available within 15s")
    return False


# ---------------------------------------------------------------------------
# Pre-authentication
# ---------------------------------------------------------------------------

def pre_auth(product: str = "grafana") -> bool:
    """Log into the product via chrome-devtools MCP tools."""
    s = spec(product)
    prompt = (
        f"Navigate to {s.url} and log in with "
        f"{s.user}/{s.password} using chrome-devtools tools. "
        f"Accept any password change prompts by keeping {s.user}/{s.password}."
    )
    result = run_claude(
        prompt,
        model=MODEL_DRIVE,
        allowed_tools="mcp__chrome-devtools__*",
        timeout=120,
    )
    if not result["success"]:
        print(f"ERROR: Pre-auth failed: {result.get('error', 'unknown')}")
        return False
    print("Pre-authentication complete")
    return True


# ---------------------------------------------------------------------------
# Fixture provisioning (Fix 5) — setup-only, UI-driven, idempotent
# ---------------------------------------------------------------------------

def provision_fixture(product: str = "grafana") -> bool:
    """Establish the deterministic seed state through the UI (setup-only).

    Arranging preconditions is setup, not verification, so the MISSION UI-only
    boundary is respected: every claim is still verified purely through the
    rendered UI. The fixture is derived from the screen taxonomy, never from the
    answer key (L3). Non-fatal: if it fails, only the complex-state screens
    become unreachable. Uses the per-product `fixture_setup_<product>.txt` prompt
    (Grafana keeps the original `fixture_setup.txt`).
    """
    s = spec(product)
    prompt_file = PROMPTS_DIR / f"fixture_setup_{product}.txt"
    if not prompt_file.exists() and product == "grafana":
        prompt_file = PROMPTS_DIR / "fixture_setup.txt"
    if not prompt_file.exists():
        print(f"WARNING: no fixture-setup prompt for {product}; skipping provisioning.")
        return True

    fixture_path = FIXTURES_DIR / product / "p1_seed_dashboard.json"
    if product == "grafana" and not fixture_path.exists():
        print(f"WARNING: fixture not found at {fixture_path}; skipping provisioning.")
        return True

    template = prompt_file.read_text(encoding="utf-8")
    prompt = (
        template
        .replace("{product_url}", s.url)
        .replace("{grafana_url}", s.url)  # back-compat token in the existing template
        .replace("{fixture_path}", str(fixture_path))
    )
    print(f"Provisioning {s.name} fixture ({s.fixture_id})...")
    result = run_claude(prompt, model=MODEL_DRIVE, allowed_tools="mcp__chrome-devtools__*,Read", timeout=600)
    if not result["success"]:
        print(f"WARNING: fixture provisioning failed: {result.get('error', 'unknown')}")
        return False
    print("Fixture provisioned.")
    return True


# ---------------------------------------------------------------------------
# Core driving
# ---------------------------------------------------------------------------

def _load_agent_prompt() -> str:
    return (PROMPTS_DIR / "agent_system.txt").read_text(encoding="utf-8")


def _load_replay_prompt() -> str:
    return (PROMPTS_DIR / "replay_procedure.txt").read_text(encoding="utf-8")


def _capture_paths(screen_id: str, product: str = "grafana") -> dict[str, Path]:
    """Product+version+fixture-namespaced Pass A capture paths (L3/L7) — claim-blind,
    so shared across clean and every mutated variant of the same page."""
    return {
        "screenshot": capture_subdir(SCREENSHOTS_DIR, product) / f"{screen_id}.png",
        "description": capture_subdir(DESCRIPTIONS_DIR, product) / f"{screen_id}.txt",
        "nav_log": capture_subdir(NAV_LOGS_DIR, product) / f"{screen_id}.txt",
        "trace": capture_subdir(TRACES_DIR, product) / f"{screen_id}.json",
        "authored": capture_subdir(TRACES_DIR, product) / f"{screen_id}.authored.json",
    }


def _replay_paths(dataset_id: str, screen_id: str, product: str = "grafana") -> dict[str, Path]:
    """Pass B replay paths, keyed BY DATASET as well — the documented procedure
    differs between clean and each mutated variant, so replays must NOT be shared."""
    d = capture_subdir(TRACES_DIR, product)
    return {
        "replay": d / f"{dataset_id}__{screen_id}.replay.json",
        "replay_authored": d / f"{dataset_id}__{screen_id}.replay.authored.json",
    }


def _build_trace(
    screen_id: str, events: list[dict], authored_path: Path, *,
    pass_type: str, product: str = "grafana",
) -> NavigationTrace:
    """Assemble a NavigationTrace from the agent-authored file (richer: resulting
    URL/title per step) and/or the stream-json MCP events (tamper-proof action
    sequence). Prefers the authored steps; falls back to the parsed action trace.
    """
    s = spec(product)
    steps: list[NavigationStep] = []
    final_url = final_title = ""

    if authored_path.exists():
        try:
            data = json.loads(authored_path.read_text(encoding="utf-8"))
            raw_steps = data.get("steps", []) if isinstance(data, dict) else data
            for i, st in enumerate(raw_steps or [], 1):
                if not isinstance(st, dict):
                    continue
                steps.append(NavigationStep(
                    step=int(st.get("step", i)),
                    action=str(st.get("action", "")),
                    target_label=str(st.get("target_label", st.get("target", ""))),
                    resulting_url=str(st.get("resulting_url", "")),
                    resulting_title=str(st.get("resulting_title", "")),
                    control_present=st.get("control_present"),
                    note=str(st.get("note", "")),
                ))
            if isinstance(data, dict):
                final_url = str(data.get("final_url", ""))
                final_title = str(data.get("final_title", ""))
        except (json.JSONDecodeError, OSError, ValueError, TypeError):
            pass

    if not steps:
        for p in parse_mcp_trace(events):
            steps.append(NavigationStep(
                step=p["step"], action=p["action"], target_label=p["target_label"],
            ))

    if not final_url and steps:
        final_url = steps[-1].resulting_url
        final_title = steps[-1].resulting_title

    return NavigationTrace(
        screen_id=screen_id, pass_type=pass_type,
        product_version=s.version, fixture_id=s.fixture_id,
        steps=steps, final_url=final_url, final_title=final_title,
    )


def _drive_call(prompt: str, timeout: int = 600) -> tuple[dict, list[dict]]:
    """Run a driving call via stream-json, falling back to json if stream-json is
    unsupported (no silent degradation — agent-authored artifacts still produced).
    """
    result = run_claude_stream(prompt, model=MODEL_DRIVE, allowed_tools=_MCP_TOOLS, timeout=timeout)
    if result.get("success"):
        return result, result.get("events", [])
    print(f"  (stream-json unavailable: {result.get('error', '?')}; falling back to --output-format json)")
    result = run_claude(prompt, model=MODEL_DRIVE, allowed_tools=_MCP_TOOLS, timeout=timeout)
    return result, []


def drive_screen(plan: DriverPlan, product: str = "grafana") -> ScreenState:
    """Pass A (discovery): reach a screen, capture its neutral state + the trace."""
    p = _capture_paths(plan.screen_id, product)

    template = _load_agent_prompt()
    prompt = (
        template
        .replace("{plan_json}", json.dumps(plan.model_dump(), indent=2))
        .replace("{screenshot_path}", str(p["screenshot"]))
        .replace("{description_path}", str(p["description"]))
        .replace("{trace_path}", str(p["authored"]))
    )

    print(f"  Driving: {plan.screen_id} — {plan.goal}")
    result, events = _drive_call(prompt)

    raw_output = result.get("raw", "")
    if result.get("error"):
        raw_output += f"\n\nERROR: {result['error']}"
    p["nav_log"].write_text(raw_output, encoding="utf-8")

    success = p["screenshot"].exists() and p["description"].exists()
    description_text = p["description"].read_text(encoding="utf-8") if p["description"].exists() else ""

    trace = _build_trace(plan.screen_id, events, p["authored"], pass_type="discovery", product=product)
    trace_path_str = ""
    if trace.steps or trace.final_url:
        p["trace"].write_text(trace.model_dump_json(indent=2), encoding="utf-8")
        trace_path_str = str(p["trace"])

    print(f"  {'OK:  ' if success else 'FAIL:'} {plan.screen_id}"
          f"{'' if success else ' — missing output files'}")

    return ScreenState(
        screen_id=plan.screen_id,
        screenshot_path=str(p["screenshot"]) if p["screenshot"].exists() else "",
        text_description=description_text,
        url=trace.final_url or plan.starting_url,
        timestamp=datetime.now(timezone.utc).isoformat(),
        navigation_log_path=str(p["nav_log"]),
        success=success,
        navigation_trace_path=trace_path_str,
    )


def replay_documented_path(plan: DriverPlan, dataset_id: str, product: str = "grafana") -> str:
    """Pass B (procedure replay): perform the documented steps as an opaque
    procedure, recording per-step whether each named control existed and where it
    led — without being told the expected outcome (L2). Serves nav_path/step-order
    verification. Keyed by dataset (the documented path differs per variant).
    Returns the replay-trace path (empty on failure).
    """
    rp = _replay_paths(dataset_id, plan.screen_id, product)
    if rp["replay"].exists():
        return str(rp["replay"])

    template = _load_replay_prompt()
    prompt = (
        template
        .replace("{plan_json}", json.dumps(plan.model_dump(), indent=2))
        .replace("{trace_path}", str(rp["replay_authored"]))
        .replace("{product_url}", spec(product).url)
        .replace("{grafana_url}", spec(product).url)  # back-compat token
    )

    print(f"  Replaying documented path: {plan.screen_id} ({dataset_id})")
    _result, events = _drive_call(prompt)

    trace = _build_trace(plan.screen_id, events, rp["replay_authored"], pass_type="replay", product=product)
    if not (trace.steps or trace.final_url):
        return ""
    rp["replay"].write_text(trace.model_dump_json(indent=2), encoding="utf-8")
    return str(rp["replay"])


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _load_claim_types(dataset_id: str) -> dict[str, str]:
    """claim_id -> type from the extracted claims (text/type/screen only — no GT, L1)."""
    path = CLAIMS_DIR / f"{dataset_id}.json"
    if not path.exists():
        return {}
    try:
        claims = json.loads(path.read_text(encoding="utf-8"))
        return {c["id"]: c.get("type", "") for c in claims}
    except (json.JSONDecodeError, OSError, KeyError):
        return {}


def _cached_state(plan: DriverPlan, p: dict[str, Path]) -> ScreenState:
    description_path = p["description"]
    return ScreenState(
        screen_id=plan.screen_id,
        screenshot_path=str(p["screenshot"]),
        text_description=description_path.read_text(encoding="utf-8") if description_path.exists() else "",
        url=plan.starting_url,
        timestamp=datetime.now(timezone.utc).isoformat(),
        navigation_log_path=str(p["nav_log"]),
        success=True,
        navigation_trace_path=str(p["trace"]) if p["trace"].exists() else "",
    )


def run(dataset_id: str, product: str = "grafana") -> list[ScreenState]:
    """Load plans and drive each screen in dependency order."""
    ensure_dirs()
    s = spec(product)

    # Fix 1: refuse to drive against a product version the GT wasn't labeled on.
    if not assert_version(product):
        print("Aborting drive: deployed product version != labeled version.")
        return []

    plans_path = PLANS_DIR / f"{dataset_id}.json"
    if not plans_path.exists():
        print(f"ERROR: Plans file not found: {plans_path}")
        return []

    raw_plans = json.loads(plans_path.read_text(encoding="utf-8"))
    plans = [DriverPlan(**p) for p in raw_plans]
    claim_types = _load_claim_types(dataset_id)

    from pipeline.plan import get_navigation_order
    ordered_plans = get_navigation_order(plans)

    results: list[ScreenState] = []
    failed_ids: set[str] = set()
    attempted = 0
    reached = 0

    print(f"\nDriving {len(ordered_plans)} screens for dataset '{dataset_id}' "
          f"({s.name} {s.version}, fixture {s.fixture_id})\n")

    for plan in ordered_plans:
        p = _capture_paths(plan.screen_id, product)
        serves_nav_path = any(claim_types.get(cid) == "nav_path" for cid in plan.claim_ids)

        # Cache hit — capture already exists for this (product, version, fixture, screen).
        if p["screenshot"].exists():
            print(f"  CACHED: {plan.screen_id}")
            results.append(_cached_state(plan, p))
            reached += 1
            if serves_nav_path:
                replay_documented_path(plan, dataset_id, product)
            continue

        # Cascade failure — parent failed, skip this one.
        if plan.parent_screen_id and plan.parent_screen_id in failed_ids:
            print(f"  SKIP:  {plan.screen_id} — parent '{plan.parent_screen_id}' failed")
            results.append(ScreenState(
                screen_id=plan.screen_id, screenshot_path="", text_description="",
                url=plan.starting_url, timestamp=datetime.now(timezone.utc).isoformat(),
                navigation_log_path="", success=False,
            ))
            failed_ids.add(plan.screen_id)
            continue

        attempted += 1
        state = drive_screen(plan, product)
        results.append(state)

        if state.success:
            reached += 1
            # Pass B for nav_path/step-order claims (Fix 2).
            if serves_nav_path:
                replay_documented_path(plan, dataset_id, product)
        else:
            failed_ids.add(plan.screen_id)

    print(f"\n--- Summary ---")
    print(f"Screens reached: {reached}/{len(ordered_plans)}")
    print(f"Screens attempted (non-cached): {attempted}")
    print(f"Failures: {len(failed_ids)}")
    if failed_ids:
        print(f"Failed screens: {', '.join(sorted(failed_ids))}")

    return results


# --- Grafana-named thin aliases (kept so existing call sites/docs don't regress) ---
def start_grafana() -> bool:
    return start_product("grafana")


def stop_grafana() -> None:
    stop_product("grafana")


def wait_for_grafana(timeout: int = 60) -> bool:
    return wait_for_product("grafana", timeout)


def get_grafana_version(timeout: int = 5) -> str | None:
    return get_product_version("grafana", timeout)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3: Drive product UI screens")
    parser.add_argument(
        "dataset_id", nargs="?", default="grafana-p1-clean",
        help="Dataset identifier (default: grafana-p1-clean)",
    )
    parser.add_argument("--product", default="grafana",
                        help="Product to drive (default: grafana)")
    parser.add_argument("--setup", action="store_true",
                        help="Start the product, enforce version, provision fixture, pre-auth")
    parser.add_argument("--teardown", action="store_true", help="Stop the product after driving")
    parser.add_argument("--no-fixture", action="store_true",
                        help="Skip fixture provisioning during --setup")
    args = parser.parse_args()

    if args.setup:
        if not start_chrome():
            sys.exit(1)
        if not start_product(args.product):
            sys.exit(1)
        if not assert_version(args.product):
            sys.exit(1)
        if not pre_auth(args.product):
            sys.exit(1)
        if not args.no_fixture:
            provision_fixture(args.product)  # non-fatal: only affects complex-state reachability

    results = run(args.dataset_id, args.product)

    if args.teardown:
        stop_product(args.product)

    if any(not s.success for s in results):
        sys.exit(1)


if __name__ == "__main__":
    main()

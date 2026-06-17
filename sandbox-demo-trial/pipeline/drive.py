"""Phase 3: Autonomous UI driving via chrome-devtools MCP.

Navigates a real product UI using AI agents, captures screenshots
and text descriptions of each target screen for downstream verification.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

from pipeline.claude_runner import run_claude
from pipeline.config import (
    CHROME_DEBUG_PORT,
    CHROME_EXE,
    DESCRIPTIONS_DIR,
    DOCKER_BIN,
    GRAFANA_CONTAINER,
    GRAFANA_HEALTH,
    GRAFANA_IMAGE,
    GRAFANA_PASS,
    GRAFANA_PORT,
    GRAFANA_URL,
    GRAFANA_USER,
    MODEL_DRIVE,
    NAV_LOGS_DIR,
    PLANS_DIR,
    PROMPTS_DIR,
    SCREENSHOTS_DIR,
    ensure_dirs,
)
from pipeline.models import DriverPlan, ScreenState


# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------

def wait_for_grafana(timeout: int = 60) -> bool:
    """Poll the Grafana health endpoint until it responds OK."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = subprocess.run(
                ["curl", "-sf", GRAFANA_HEALTH],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                print(f"Grafana healthy at {GRAFANA_URL}")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        time.sleep(2)
    print(f"ERROR: Grafana did not become healthy within {timeout}s")
    return False


def start_grafana() -> bool:
    """Start the Grafana container and wait for it to be healthy."""
    subprocess.run(
        [DOCKER_BIN, "rm", "-f", GRAFANA_CONTAINER],
        capture_output=True, text=True,
    )
    result = subprocess.run(
        [
            DOCKER_BIN, "run", "-d",
            "-p", f"{GRAFANA_PORT}:3000",
            "--name", GRAFANA_CONTAINER,
            GRAFANA_IMAGE,
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: Failed to start Grafana: {result.stderr.strip()}")
        return False
    print(f"Started container {GRAFANA_CONTAINER}")
    return wait_for_grafana()


def stop_grafana() -> None:
    """Stop and remove the Grafana container."""
    subprocess.run(
        [DOCKER_BIN, "rm", "-f", GRAFANA_CONTAINER],
        capture_output=True, text=True,
    )
    print(f"Stopped and removed container {GRAFANA_CONTAINER}")


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

    # Wait for CDP to become available
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

def pre_auth() -> bool:
    """Log into Grafana via chrome-devtools MCP tools."""
    prompt = (
        f"Navigate to {GRAFANA_URL} and log in with "
        f"{GRAFANA_USER}/{GRAFANA_PASS} using chrome-devtools tools. "
        "Accept any password change prompts by keeping admin/admin."
    )
    result = run_claude(
        prompt,
        model=MODEL_DRIVE,
        allowed_tools="mcp:chrome-devtools",
        timeout=120,
    )
    if not result["success"]:
        print(f"ERROR: Pre-auth failed: {result.get('error', 'unknown')}")
        return False
    print("Pre-authentication complete")
    return True


# ---------------------------------------------------------------------------
# Core driving
# ---------------------------------------------------------------------------

def _load_agent_prompt() -> str:
    """Load the agent system prompt template."""
    path = PROMPTS_DIR / "agent_system.txt"
    return path.read_text(encoding="utf-8")


def drive_screen(plan: DriverPlan) -> ScreenState:
    """Drive the browser to a single screen and capture its state."""
    screenshot_path = SCREENSHOTS_DIR / f"{plan.screen_id}.png"
    description_path = DESCRIPTIONS_DIR / f"{plan.screen_id}.txt"
    nav_log_path = NAV_LOGS_DIR / f"{plan.screen_id}.txt"

    template = _load_agent_prompt()
    prompt = template.format(
        plan_json=json.dumps(plan.model_dump(), indent=2),
        screenshot_path=str(screenshot_path),
        description_path=str(description_path),
    )

    print(f"  Driving: {plan.screen_id} — {plan.goal}")
    result = run_claude(
        prompt,
        model=MODEL_DRIVE,
        allowed_tools="mcp:chrome-devtools,Write,Read",
        timeout=600,
    )

    # Save raw output as navigation log
    raw_output = result.get("raw", "")
    if result.get("error"):
        raw_output += f"\n\nERROR: {result['error']}"
    nav_log_path.write_text(raw_output, encoding="utf-8")

    # Check whether the agent produced the expected files
    success = screenshot_path.exists() and description_path.exists()

    description_text = ""
    if description_path.exists():
        description_text = description_path.read_text(encoding="utf-8")

    url = plan.starting_url
    if not success:
        print(f"  FAIL: {plan.screen_id} — missing output files")
    else:
        print(f"  OK:   {plan.screen_id}")

    return ScreenState(
        screen_id=plan.screen_id,
        screenshot_path=str(screenshot_path) if screenshot_path.exists() else "",
        text_description=description_text,
        url=url,
        timestamp=datetime.now(timezone.utc).isoformat(),
        navigation_log_path=str(nav_log_path),
        success=success,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run(dataset_id: str) -> list[ScreenState]:
    """Load plans and drive each screen in dependency order."""
    ensure_dirs()

    plans_path = PLANS_DIR / f"{dataset_id}.json"
    if not plans_path.exists():
        print(f"ERROR: Plans file not found: {plans_path}")
        return []

    raw_plans = json.loads(plans_path.read_text(encoding="utf-8"))
    plans = [DriverPlan(**p) for p in raw_plans]

    # Import here to avoid circular imports and allow plan.py to not exist yet
    from pipeline.plan import get_navigation_order

    ordered_plans = get_navigation_order(plans)

    results: list[ScreenState] = []
    failed_ids: set[str] = set()
    attempted = 0
    reached = 0

    print(f"\nDriving {len(ordered_plans)} screens for dataset '{dataset_id}'\n")

    for plan in ordered_plans:
        # Cache hit — screenshot already exists
        if (SCREENSHOTS_DIR / f"{plan.screen_id}.png").exists():
            print(f"  CACHED: {plan.screen_id}")
            description_path = DESCRIPTIONS_DIR / f"{plan.screen_id}.txt"
            results.append(ScreenState(
                screen_id=plan.screen_id,
                screenshot_path=str(SCREENSHOTS_DIR / f"{plan.screen_id}.png"),
                text_description=description_path.read_text(encoding="utf-8") if description_path.exists() else "",
                url=plan.starting_url,
                timestamp=datetime.now(timezone.utc).isoformat(),
                navigation_log_path=str(NAV_LOGS_DIR / f"{plan.screen_id}.txt"),
                success=True,
            ))
            reached += 1
            continue

        # Cascade failure — parent failed, skip this one
        if plan.parent_screen_id and plan.parent_screen_id in failed_ids:
            print(f"  SKIP:  {plan.screen_id} — parent '{plan.parent_screen_id}' failed")
            results.append(ScreenState(
                screen_id=plan.screen_id,
                screenshot_path="",
                text_description="",
                url=plan.starting_url,
                timestamp=datetime.now(timezone.utc).isoformat(),
                navigation_log_path="",
                success=False,
            ))
            failed_ids.add(plan.screen_id)
            continue

        attempted += 1
        state = drive_screen(plan)
        results.append(state)

        if state.success:
            reached += 1
        else:
            failed_ids.add(plan.screen_id)

    print(f"\n--- Summary ---")
    print(f"Screens reached: {reached}/{len(ordered_plans)}")
    print(f"Screens attempted (non-cached): {attempted}")
    print(f"Failures: {len(failed_ids)}")
    if failed_ids:
        print(f"Failed screens: {', '.join(sorted(failed_ids))}")

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3: Drive product UI screens")
    parser.add_argument(
        "dataset_id",
        nargs="?",
        default="grafana-p1-clean",
        help="Dataset identifier (default: grafana-p1-clean)",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Start Grafana and pre-authenticate before driving",
    )
    parser.add_argument(
        "--teardown",
        action="store_true",
        help="Stop Grafana after driving",
    )
    args = parser.parse_args()

    if args.setup:
        if not start_chrome():
            sys.exit(1)
        if not start_grafana():
            sys.exit(1)
        if not pre_auth():
            sys.exit(1)

    results = run(args.dataset_id)

    if args.teardown:
        stop_grafana()

    # Exit with error if any screens failed
    if any(not s.success for s in results):
        sys.exit(1)


if __name__ == "__main__":
    main()

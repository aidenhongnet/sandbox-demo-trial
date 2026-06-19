from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Windows stdout/stderr default to the locale codepage (cp1252) when redirected;
# LLM-generated text routinely contains non-cp1252 Unicode (→, —, smart quotes),
# so a plain print() of model output raises UnicodeEncodeError and aborts a phase
# mid-run (it killed the first m1 E2E drive at screen 1). Force UTF-8 (replace on
# any oddity) on our streams so model text can never crash the pipeline.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # non-reconfigurable stream (e.g. piped)
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent


def _find_tool(name: str, *fallbacks: str) -> str:
    """Return first resolvable path for a tool: PATH lookup, then absolute fallbacks."""
    found = shutil.which(name)
    if found:
        return found
    for fb in fallbacks:
        if Path(fb).exists():
            return fb
    return name  # let subprocess surface a clear FileNotFoundError

# --- Tool binaries (per-user installs on Windows; shutil.which first, then known paths) ---
_HOME = Path.home()
DOCKER_BIN = _find_tool(
    "docker",
    str(_HOME / "AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe"),
)
CHROME_EXE = _find_tool(
    "chrome",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    str(_HOME / "AppData/Local/Google/Chrome/Application/chrome.exe"),
)

# --- Paths (declared early; ProductSpec.ontology_path references FIXTURES_DIR lazily) ---
DATASET_DIR = ROOT_DIR / "dataset"
SOURCES_DIR = DATASET_DIR / "sources"
MANIFEST_PATH = DATASET_DIR / "manifest.jsonl"

PIPELINE_DIR = ROOT_DIR / "pipeline"
PROMPTS_DIR = PIPELINE_DIR / "prompts"

RESULTS_DIR = ROOT_DIR / "results"
# Fixture assets (deterministic seed state, per-product screen ontology) live
# in-repo, not results.
FIXTURES_DIR = ROOT_DIR / "fixtures"

# Dedicated Chrome profile for CDP so we get a separate debuggable instance even
# when the user already has Chrome running (a fresh --user-data-dir forces a new
# process with the remote-debugging port actually open).
CHROME_USER_DATA_DIR = RESULTS_DIR / "chrome-profile"
CLAIMS_DIR = RESULTS_DIR / "claims"
PLANS_DIR = RESULTS_DIR / "plans"
SCREENSHOTS_DIR = RESULTS_DIR / "screenshots"
DESCRIPTIONS_DIR = RESULTS_DIR / "descriptions"
NAV_LOGS_DIR = RESULTS_DIR / "navigation_logs"
TRACES_DIR = RESULTS_DIR / "traces"
VERDICTS_DIR = RESULTS_DIR / "verdicts"


# ---------------------------------------------------------------------------
# Product registry (generalization surface — plan §2.1)
# ---------------------------------------------------------------------------
# The pipeline is product-parametric: every phase receives a `product` string and
# looks its deployment up here. Version always comes from this registry (config),
# never from the manifest, so the prediction modules stay ground-truth-blind and
# the Fix-1 preflight is a config↔manifest equality check.
@dataclass(frozen=True)
class ProductSpec:
    name: str
    version: str          # deployed==labeled build; == each manifest entry's product_version
    image: str
    container: str
    port: int
    user: str
    password: str
    fixture_id: str       # identifies the provisioned env state captures are keyed on
    # Bring-up shape: "run" (docker run) | "compose" (docker compose up).
    bring_up: str = "run"
    # Extra args appended after the image on `docker run` (e.g. Keycloak's start-dev).
    run_args: tuple[str, ...] = ()
    # Environment passed to the container (e.g. Keycloak admin bootstrap).
    env: tuple[tuple[str, str], ...] = ()
    # Multi-container compose file (NetBox), resolved under FIXTURES_DIR/<name>/.
    compose_file: str | None = None
    # Reachability path polled until the product is up.
    health_path: str = "/api/health"
    # How to read the running version: "grafana_health" | "netbox_status" |
    # "keycloak_serverinfo". The drive-phase adapter dispatches on this (plan §2.2).
    version_probe: str = "grafana_health"

    @property
    def url(self) -> str:
        return f"http://localhost:{self.port}"

    @property
    def health_url(self) -> str:
        return f"{self.url}{self.health_path}"

    @property
    def image_tag(self) -> str:
        """Just the tag portion of `image` (used as the version-probe fallback)."""
        return self.image.rsplit(":", 1)[-1].lstrip("v")

    @property
    def ontology_path(self) -> Path:
        return FIXTURES_DIR / self.name / "screen_ontology.json"


# Pinned, pull-verified builds (plan §3). Grafana is live + validated; Keycloak and
# NetBox specs are pre-pinned here so the registry is complete, but their bring-up /
# fixtures / ontology are completed mechanically in their own Stage-2 builds.
PRODUCTS: dict[str, ProductSpec] = {
    "grafana": ProductSpec(
        name="grafana",
        # Product version is an explicit, enforced variable (Fix 1): the deployed
        # container is pinned to the exact version the ground truth was labeled
        # against, and drive.py refuses to run on a mismatch. The grafana-p1 doc
        # describes Grafana 13.0's Dynamic Dashboards (Add new element, Auto grid
        # layout, Show/hide rules), GA 2026-04-08; 13.0.2 is the latest 13.0.x patch.
        version="13.0.2",
        image="grafana/grafana:13.0.2",
        container="grafana-mvp",
        port=3000,
        user="admin",
        password="admin",
        fixture_id="grafana-p1-seed-v1",
        bring_up="run",
        health_path="/api/health",
        version_probe="grafana_health",
    ),
    "keycloak": ProductSpec(
        name="keycloak",
        version="26.4.0",
        image="quay.io/keycloak/keycloak:26.4.0",
        container="keycloak-mvp",
        port=8080,
        user="admin",
        password="admin",
        fixture_id="keycloak-seed-v1",
        bring_up="run",
        run_args=("start-dev",),
        env=(("KC_BOOTSTRAP_ADMIN_USERNAME", "admin"),
             ("KC_BOOTSTRAP_ADMIN_PASSWORD", "admin")),
        health_path="/",
        version_probe="keycloak_serverinfo",
    ),
    "netbox": ProductSpec(
        name="netbox",
        version="4.4.0",
        image="netboxcommunity/netbox:v4.4.0",
        container="netbox-mvp",
        port=8000,
        user="admin",
        password="admin",
        fixture_id="netbox-seed-v1",
        bring_up="compose",
        compose_file="docker-compose.yml",
        health_path="/api/status/",
        version_probe="netbox_status",
    ),
}


def spec(product: str) -> ProductSpec:
    """Look up a ProductSpec, with a clear error for an unknown product."""
    try:
        return PRODUCTS[product]
    except KeyError:
        raise ValueError(
            f"Unknown product '{product}'. Known: {sorted(PRODUCTS)}"
        ) from None


# --- Grafana aliases (kept so existing Grafana call sites don't regress) ---
_GRAFANA = PRODUCTS["grafana"]
PRODUCT_VERSION = _GRAFANA.version
GRAFANA_IMAGE = _GRAFANA.image
GRAFANA_CONTAINER = _GRAFANA.container
GRAFANA_PORT = _GRAFANA.port
GRAFANA_URL = _GRAFANA.url
GRAFANA_HEALTH = _GRAFANA.health_url
GRAFANA_USER = _GRAFANA.user
GRAFANA_PASS = _GRAFANA.password
# Identifies the provisioned environment state that captures are keyed on, next
# to PRODUCT_VERSION (L3/L7). Bump when the fixture definition changes so stale
# captures are never reused.
FIXTURE_ID = _GRAFANA.fixture_id

# --- Chrome ---
CHROME_DEBUG_PORT = 9222

# --- Models (all invocations via claude -p) ---
MODEL_EXTRACT = "haiku"
MODEL_PLAN = "sonnet"
MODEL_DRIVE = "sonnet"
MODEL_VERIFY = "haiku"
# Claim decomposition (Fix 3.1). Keep on Haiku by default; escalate to "sonnet"
# only if DEV-set calibration shows Haiku can't reliably split compound claims.
MODEL_DECOMPOSE = "haiku"
# Semantic claim matcher (plan §4 — the GT-side LLM judge in metrics.py). DEV
# calibration on grafana-p1 showed Haiku is unreliable disambiguating clusters of
# closely-related claims (it nulls clear matches under load, ~0.6-0.8 recall with
# high variance); Sonnet matches them reliably (~0.9+). The matcher runs once per
# dataset and is cached, so the extra cost is negligible.
MODEL_MATCH = "sonnet"

# --- Verifier behavior (Fix 3 / Fix 4) ---
# Self-consistency: run each verify call N times and majority-vote (Fix 3.2).
# Stabilizes verdicts (claude -p exposes no temperature) and yields a calibrated
# confidence = vote fraction. Split votes -> uncertain.
VERIFY_SELF_CONSISTENCY_N = 3
# Real image input for visual_state evidence (Fix 4). If the DRIVER's smoke test
# shows headless `claude -p` + Read cannot ingest a PNG, set this False: visual-
# dependent atoms then return UNCERTAIN (honest) instead of a fabricated verdict.
# The fake "screenshot attached" note is never restored.
IMAGE_INPUT_ENABLED = True

# Captures (screenshots/descriptions/traces/nav_logs) are a pure function of
# (product, product_version, fixture_id, screen_id) — never of dataset_id/claim_id
# (L3/L7). Verdict/claim/plan outputs stay flat: verdicts are claim-specific (L7).
CAPTURE_DIRS = [SCREENSHOTS_DIR, DESCRIPTIONS_DIR, NAV_LOGS_DIR, TRACES_DIR]
FLAT_RESULT_DIRS = [CLAIMS_DIR, PLANS_DIR, VERDICTS_DIR]
ALL_RESULT_DIRS = FLAT_RESULT_DIRS + CAPTURE_DIRS


def capture_subdir(base: Path, product: str = "grafana", *,
                   product_version: str | None = None,
                   fixture_id: str | None = None) -> Path:
    """Product+version+fixture-namespaced capture directory (L3/L7 cache key).

    Version and fixture default to the product's ProductSpec (config is the single
    source of truth), so callers only pass `product`. The product segment prevents
    cross-product capture collisions when the same version/fixture id is reused.
    """
    s = PRODUCTS[product]
    pv = product_version or s.version
    fx = fixture_id or s.fixture_id
    d = base / product / pv / fx
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_dirs() -> None:
    for d in ALL_RESULT_DIRS:
        d.mkdir(parents=True, exist_ok=True)

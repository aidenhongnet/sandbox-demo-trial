from __future__ import annotations

import shutil
from pathlib import Path

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

# --- Docker / Grafana ---
GRAFANA_IMAGE = "grafana/grafana:11.6.0"
GRAFANA_CONTAINER = "grafana-mvp"
GRAFANA_PORT = 3000
GRAFANA_URL = f"http://localhost:{GRAFANA_PORT}"
GRAFANA_HEALTH = f"{GRAFANA_URL}/api/health"
GRAFANA_USER = "admin"
GRAFANA_PASS = "admin"

# --- Chrome ---
CHROME_DEBUG_PORT = 9222

# --- Models (all invocations via claude -p) ---
MODEL_EXTRACT = "haiku"
MODEL_PLAN = "sonnet"
MODEL_DRIVE = "sonnet"
MODEL_VERIFY = "haiku"

# --- Paths ---
DATASET_DIR = ROOT_DIR / "dataset"
SOURCES_DIR = DATASET_DIR / "sources"
MANIFEST_PATH = DATASET_DIR / "manifest.jsonl"

PIPELINE_DIR = ROOT_DIR / "pipeline"
PROMPTS_DIR = PIPELINE_DIR / "prompts"

RESULTS_DIR = ROOT_DIR / "results"
CLAIMS_DIR = RESULTS_DIR / "claims"
PLANS_DIR = RESULTS_DIR / "plans"
SCREENSHOTS_DIR = RESULTS_DIR / "screenshots"
DESCRIPTIONS_DIR = RESULTS_DIR / "descriptions"
NAV_LOGS_DIR = RESULTS_DIR / "navigation_logs"
VERDICTS_DIR = RESULTS_DIR / "verdicts"

ALL_RESULT_DIRS = [
    CLAIMS_DIR, PLANS_DIR, SCREENSHOTS_DIR,
    DESCRIPTIONS_DIR, NAV_LOGS_DIR, VERDICTS_DIR,
]


def ensure_dirs() -> None:
    for d in ALL_RESULT_DIRS:
        d.mkdir(parents=True, exist_ok=True)

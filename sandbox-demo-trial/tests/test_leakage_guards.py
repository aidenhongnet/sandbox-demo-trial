"""Leakage guard L1 — prediction modules must stay ground-truth-blind.

`pipeline/metrics.py` is the single permitted reader of the manifest ground-truth
fields (`is_correct`, `expected_findings`, `mutation`). The prediction modules —
`extract`, `plan`, `drive`, `verify` — must never read those fields or import the
GT loader, or they could (accidentally or otherwise) manufacture agreement with
the answer key and silently destroy the system's value.

Runs as pytest OR standalone: `python tests/test_leakage_guards.py`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PIPELINE = ROOT / "pipeline"

PREDICTION_MODULES = ["extract.py", "plan.py", "drive.py", "verify.py"]
# Substrings that only appear when a module touches ground-truth labels.
FORBIDDEN = ["is_correct", "expected_findings", "_load_ground_truth", "MANIFEST_PATH"]


def _src(name: str) -> str:
    return (PIPELINE / name).read_text(encoding="utf-8")


def test_prediction_modules_are_gt_blind() -> None:
    for mod in PREDICTION_MODULES:
        src = _src(mod)
        for tok in FORBIDDEN:
            assert tok not in src, f"{mod} references GT token {tok!r} (L1 violation)"
        assert not re.search(r"\bmutation\b", src), f"{mod} references 'mutation' (L1 violation)"


def test_metrics_is_the_sole_gt_reader() -> None:
    assert "_load_ground_truth" in _src("metrics.py")


def test_orchestrator_delegates_gt_scoring() -> None:
    # The orchestrator may read the manifest for prediction *inputs* (doc content),
    # but it must not compute labels itself — no is_correct, no GT loader.
    src = _src("orchestrator.py")
    assert "is_correct" not in src
    assert "_load_ground_truth" not in src


def test_no_runtime_gt_loader_import() -> None:
    # Best-effort: if the prediction modules import cleanly (their deps are present),
    # assert none of them pulled the GT loader into their namespace.
    import importlib

    for mod in ("extract", "plan", "drive", "verify"):
        try:
            m = importlib.import_module(f"pipeline.{mod}")
        except Exception:
            continue  # import-time deps unavailable; the source scan already covers L1
        assert not hasattr(m, "_load_ground_truth"), f"pipeline.{mod} imported the GT loader"


if __name__ == "__main__":
    test_prediction_modules_are_gt_blind()
    test_metrics_is_the_sole_gt_reader()
    test_orchestrator_delegates_gt_scoring()
    test_no_runtime_gt_loader_import()
    print("L1 leakage guards: OK")

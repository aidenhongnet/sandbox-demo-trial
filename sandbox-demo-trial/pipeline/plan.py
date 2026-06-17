"""Phase 2: Driver Plan Generation.

Groups extracted claims by target screen, builds navigation plans
for each screen via Claude, and orders them by dependency depth.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from pipeline.claude_runner import run_claude
from pipeline.config import (
    CLAIMS_DIR,
    GRAFANA_PASS,
    GRAFANA_URL,
    GRAFANA_USER,
    MODEL_PLAN,
    PLANS_DIR,
    PROMPTS_DIR,
    ensure_dirs,
)
from pipeline.models import DriverPlan, ExtractedClaim

# ---------------------------------------------------------------------------
# Screen dependency graph for Grafana p1
# Keys are screen names (matching target_screen in claims); values are parent.
# ---------------------------------------------------------------------------
GRAFANA_P1_DEPS: dict[str, str | None] = {
    "Home": None,
    "Dashboards list": "Home",
    "New Dashboard": "Dashboards list",
    "New Dashboard (edit mode)": "New Dashboard",
    "New panel options": "New Dashboard",
    "Panel edit mode": "New panel options",
    "Panel edit mode - Queries tab": "Panel edit mode",
    "Panel edit mode - Visualization picker": "Panel edit mode",
    "Panel editor > Standard options": "Panel edit mode",
    "Dashboard edit mode - toolbar": "New Dashboard",
    "Dashboard sidebar": "New Dashboard",
    "Content outline": "New Dashboard",
    "Dashboard settings - Layout": "New Dashboard",
    "Auto grid layout settings": "Dashboard settings - Layout",
    "Panel sidebar - Repeat options": "New Dashboard",
    "Panel sidebar - Show/hide rules": "New Dashboard",
    "Show/hide rules - Template variable rule": "Panel sidebar - Show/hide rules",
    "Show/hide rules - Match rules": "Panel sidebar - Show/hide rules",
    "Dashboard edit mode - Save menu": "New Dashboard",
    "Dashboard view mode - toolbar": "New Dashboard",
}


def _depth(screen: str, deps: dict[str, str | None]) -> int:
    """Return navigation depth (0 for root)."""
    d = 0
    cur = screen
    while deps.get(cur) is not None:
        cur = deps[cur]  # type: ignore[assignment]
        d += 1
    return d


def _screen_to_id(screen: str) -> str:
    """Convert a screen name to a slug-style screen_id."""
    slug = screen.lower().replace(" ", "-")
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def _find_parent_id(
    screen: str,
    deps: dict[str, str | None],
    screen_id_map: dict[str, str],
) -> str | None:
    """Look up the parent screen_id for a given screen name."""
    parent_name = deps.get(screen)
    if parent_name is None:
        return None
    return screen_id_map.get(parent_name)


def _load_claims(dataset_id: str) -> list[ExtractedClaim]:
    path = CLAIMS_DIR / f"{dataset_id}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [ExtractedClaim(**c) for c in raw]


def _group_by_screen(claims: list[ExtractedClaim]) -> dict[str, list[ExtractedClaim]]:
    groups: dict[str, list[ExtractedClaim]] = defaultdict(list)
    for c in claims:
        groups[c.target_screen].append(c)
    return dict(groups)


def _build_product_context() -> str:
    return (
        f"Product: Grafana\n"
        f"Base URL: {GRAFANA_URL}\n"
        f"Login credentials: username={GRAFANA_USER}, password={GRAFANA_PASS}\n"
        f"The product is running locally in a Docker container."
    )


def _load_prompt_template() -> str:
    return (PROMPTS_DIR / "plan_navigation.txt").read_text(encoding="utf-8")


def _coerce_plan_fields(data: dict) -> dict:
    """Normalize LLM response fields to match DriverPlan schema."""
    for str_field in ("goal", "what_to_capture", "starting_url"):
        if isinstance(data.get(str_field), list):
            data[str_field] = " ".join(str(x) for x in data[str_field])
    for list_field in ("navigation_hints", "preconditions", "claim_ids"):
        val = data.get(list_field)
        if isinstance(val, str):
            data[list_field] = [val]
        elif val is None:
            data[list_field] = []
    return data


def _generate_plan(
    screen: str,
    claims: list[ExtractedClaim],
    template: str,
    product_context: str,
) -> DriverPlan:
    """Call Claude to generate a DriverPlan for one screen group."""
    claims_json = json.dumps([c.model_dump() for c in claims], indent=2)
    prompt = template.replace("{claims_json}", claims_json).replace("{product_context}", product_context)

    result = run_claude(prompt, model=MODEL_PLAN, json_output=True)

    if not result["success"]:
        raise RuntimeError(f"Plan generation failed for '{screen}': {result.get('error', 'unknown')}")

    parsed = result.get("parsed")
    if parsed is None:
        raw = result.get("raw", "")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            raise RuntimeError(f"Could not parse plan JSON for '{screen}': {raw[:500]}")

    return DriverPlan(**_coerce_plan_fields(parsed))


def get_navigation_order(plans: list[DriverPlan]) -> list[DriverPlan]:
    """Sort plans by dependency: roots first, then children.

    Uses parent_screen_id to build a topological ordering.
    Plans without a parent come first, followed by their dependents.
    """
    by_id: dict[str, DriverPlan] = {p.screen_id: p for p in plans}
    visited: set[str] = set()
    ordered: list[DriverPlan] = []

    def visit(plan: DriverPlan) -> None:
        if plan.screen_id in visited:
            return
        # Visit parent first if it exists.
        if plan.parent_screen_id and plan.parent_screen_id in by_id:
            visit(by_id[plan.parent_screen_id])
        visited.add(plan.screen_id)
        ordered.append(plan)

    for p in plans:
        visit(p)

    return ordered


def run(dataset_id: str = "grafana-p1-clean") -> list[DriverPlan]:
    """Generate driver plans for all screens in a dataset."""
    ensure_dirs()

    claims = _load_claims(dataset_id)
    groups = _group_by_screen(claims)

    # Sort screen groups by navigation depth (shallow first).
    sorted_screens = sorted(groups.keys(), key=lambda s: _depth(s, GRAFANA_P1_DEPS))

    # Pre-compute screen_id map for parent lookups.
    screen_id_map: dict[str, str] = {s: _screen_to_id(s) for s in sorted_screens}

    template = _load_prompt_template()
    product_context = _build_product_context()

    plans: list[DriverPlan] = []
    for screen in sorted_screens:
        screen_claims = groups[screen]
        print(f"  Planning: {screen} ({len(screen_claims)} claims)")

        plan = _generate_plan(screen, screen_claims, template, product_context)

        # Enforce consistent screen_id and parent linkage.
        plan.screen_id = screen_id_map[screen]
        plan.parent_screen_id = _find_parent_id(screen, GRAFANA_P1_DEPS, screen_id_map)

        plans.append(plan)

    # Write output.
    out_path = PLANS_DIR / f"{dataset_id}.json"
    out_path.write_text(
        json.dumps([p.model_dump() for p in plans], indent=2),
        encoding="utf-8",
    )
    print(f"  Wrote {len(plans)} plans to {out_path}")

    return get_navigation_order(plans)


if __name__ == "__main__":
    dataset = sys.argv[1] if len(sys.argv) > 1 else "grafana-p1-clean"
    ordered = run(dataset)
    print(f"\nNavigation order ({len(ordered)} screens):")
    for i, p in enumerate(ordered, 1):
        parent = f" (after {p.parent_screen_id})" if p.parent_screen_id else ""
        print(f"  {i}. {p.screen_id}{parent}")

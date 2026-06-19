"""Phase 4: Claim Verification.

Verifies each claim against the captured screen state with three guards against
the failure modes from the first run:
  * Fix 3.1 — decompose compound claims into atoms (tagged ui_label / functional
    / visual / nav) and aggregate, so one contradicted atom fails the claim while
    a parenthetical functional description is never judged as on-screen text.
  * Fix 3.2 — N-way self-consistency: run each verify call N times, majority-vote,
    confidence = vote fraction (claude -p has no temperature knob).
  * Fix 2 / Fix 4 — nav atoms are judged against the navigation *trace* (not the
    destination); visual atoms are judged against a real screenshot or abstain.

The verifier never sees ground-truth fields (L1) and the screenshot it reads is
the driver's neutral, unannotated capture (L2).
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from pipeline import metrics
from pipeline.config import (
    CLAIMS_DIR,
    DESCRIPTIONS_DIR,
    IMAGE_INPUT_ENABLED,
    MODEL_DECOMPOSE,
    MODEL_VERIFY,
    PROMPTS_DIR,
    SCREENSHOTS_DIR,
    TRACES_DIR,
    VERDICTS_DIR,
    VERIFY_SELF_CONSISTENCY_N,
    capture_subdir,
    ensure_dirs,
)
from pipeline.claude_runner import run_claude
from pipeline.models import ExtractedClaim, Verdict

# Map a claim's coarse type to the atom sub_type used when decomposition is skipped.
_TYPE_TO_SUBTYPE = {
    "nav_path": "nav",
    "visual_state": "visual",
    "ui_element": "ui_label",
    "field_value": "ui_label",
    "behavior": "functional",
}


def _slugify(screen_name: str) -> str:
    slug = screen_name.lower().replace(" ", "-")
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    return re.sub(r"-+", "-", slug).strip("-")


def _load_claims(dataset_id: str) -> list[ExtractedClaim]:
    path = CLAIMS_DIR / f"{dataset_id}.json"
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return [ExtractedClaim(**c) for c in raw]


def _load_screen_states(dataset_id: str, product: str = "grafana") -> dict[str, dict]:
    """screen_id -> {description, screenshot, discovery_trace, replay_trace}.

    Pass A captures (description/screenshot/discovery trace) come from the
    product+version+fixture-namespaced dirs and are shared across clean/variants
    (L3/L7). The Pass B replay trace is keyed by dataset (the documented path
    differs per variant), so it is looked up with the dataset prefix.
    """
    desc_dir = capture_subdir(DESCRIPTIONS_DIR, product)
    shot_dir = capture_subdir(SCREENSHOTS_DIR, product)
    trace_dir = capture_subdir(TRACES_DIR, product)

    screens: dict[str, dict] = {}
    for desc_file in desc_dir.glob("*.txt"):
        sid = desc_file.stem
        shot = shot_dir / f"{sid}.png"
        disc = trace_dir / f"{sid}.json"
        replay = trace_dir / f"{dataset_id}__{sid}.replay.json"
        screens[sid] = {
            "description": desc_file.read_text(encoding="utf-8"),
            "screenshot": shot if shot.exists() else None,
            "discovery_trace": disc if disc.exists() else None,
            "replay_trace": replay if replay.exists() else None,
        }
    return screens


def _load_template(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def _format_trace(path: Path | None) -> str:
    """Render a NavigationTrace JSON file as readable step text for the prompt."""
    if not path or not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ""
    lines = [f"pass={data.get('pass_type', '?')} "
             f"final={data.get('final_title', '')!r} ({data.get('final_url', '')})"]
    for s in data.get("steps", []):
        cp = s.get("control_present")
        cp_str = "" if cp is None else f" control_present={cp}"
        note = f" note: {s.get('note')}" if s.get("note") else ""
        lines.append(
            f"  {s.get('step')}. [{s.get('action')}] {s.get('target_label')!r} -> "
            f"{s.get('resulting_title', '')!r} ({s.get('resulting_url', '')}){cp_str}{note}"
        )
    return "\n".join(lines)


def decompose_claim(claim: ExtractedClaim, template: str) -> list[dict]:
    """Split a claim into atoms (Fix 3.1). Falls back to a single typed atom."""
    fallback = [{"text": claim.text, "sub_type": _TYPE_TO_SUBTYPE.get(claim.type, "ui_label")}]
    prompt = template.replace("{claim_json}", json.dumps(claim.model_dump(), indent=2))
    resp = run_claude(prompt, model=MODEL_DECOMPOSE, json_output=True)
    parsed = resp.get("parsed")
    if isinstance(parsed, dict):
        parsed = parsed.get("atoms") or parsed.get("result")
    if not isinstance(parsed, list) or not parsed:
        return fallback
    atoms = []
    for a in parsed[:12]:  # cap pathological decompositions
        if isinstance(a, dict) and a.get("text"):
            st = a.get("sub_type", "ui_label")
            atoms.append({"text": str(a["text"]),
                          "sub_type": st if st in {"ui_label", "functional", "visual", "nav"} else "ui_label"})
    return atoms or fallback


def _aggregate(atom_results: list[str]) -> str:
    """true iff all atoms true; false if any false; else uncertain (Fix 3.1)."""
    if not atom_results:
        return "uncertain"
    if any(r == "false" for r in atom_results):
        return "false"
    if all(r == "true" for r in atom_results):
        return "true"
    return "uncertain"


def _verify_once(
    claim: ExtractedClaim,
    atoms: list[dict],
    description: str,
    template: str,
    *,
    evidence_note: str,
    use_image: bool,
    screenshot_path: Path | None,
) -> dict:
    """One verify call: returns {result, atoms:[{text,sub_type,result,evidence}], reasoning}."""
    note = evidence_note
    allowed = None
    if use_image and screenshot_path is not None:
        note += (f"\n## Screenshot\nA screenshot of this screen is saved at "
                 f"{screenshot_path}. Use the Read tool to open and view it, then judge "
                 f"visual atoms from the image.")
        allowed = "Read"

    prompt = (
        template
        .replace("{claim_json}", json.dumps(claim.model_dump(), indent=2))
        .replace("{atoms_json}", json.dumps(atoms, indent=2))
        .replace("{screen_description}", description)
        .replace("{evidence_note}", note)
    )
    resp = run_claude(prompt, model=MODEL_VERIFY, json_output=True, allowed_tools=allowed)
    parsed = resp.get("parsed")
    if not isinstance(parsed, dict):
        return {"result": "uncertain", "atoms": [], "reasoning": "Unparseable verifier response.", "evidence": ""}

    atom_out = parsed.get("atoms")
    if not isinstance(atom_out, list) or not atom_out:
        return {"result": "uncertain", "atoms": [], "reasoning": parsed.get("reasoning", ""), "evidence": ""}

    results = [str(a.get("result", "uncertain")).lower() for a in atom_out if isinstance(a, dict)]
    return {
        "result": _aggregate(results),
        "atoms": atom_out,
        "reasoning": parsed.get("reasoning", ""),
    }


def _self_consistent_verify(
    claim: ExtractedClaim,
    atoms: list[dict],
    description: str,
    template: str,
    *,
    evidence_note: str,
    use_image: bool,
    screenshot_path: Path | None,
    n: int = VERIFY_SELF_CONSISTENCY_N,
) -> tuple[str, float, list[dict], str, str]:
    """Run the verify call n times and majority-vote (Fix 3.2).

    Returns (result, confidence=vote_fraction, winning_atoms, reasoning, votes_str).
    A split vote (no strict majority) -> uncertain.
    """
    runs = [
        _verify_once(claim, atoms, description, template,
                     evidence_note=evidence_note, use_image=use_image,
                     screenshot_path=screenshot_path)
        for _ in range(max(1, n))
    ]
    counts = Counter(r["result"] for r in runs)
    top_result, top_votes = counts.most_common(1)[0]

    # Require a strict majority; otherwise abstain.
    if top_votes * 2 <= len(runs) and len(counts) > 1:
        result = "uncertain"
        votes_str = "split"
    else:
        result = top_result
        votes_str = f"{top_votes}/{len(runs)}"
    confidence = round(top_votes / len(runs), 2)

    winning = next((r for r in runs if r["result"] == result), runs[0])
    return result, confidence, winning.get("atoms", []), winning.get("reasoning", ""), votes_str


def _first_failing_atom(atoms: list[dict]) -> tuple[str, str]:
    """Return (text, evidence) of the first FALSE atom, else first UNCERTAIN, else ('','')."""
    for target in ("false", "uncertain"):
        for a in atoms:
            if isinstance(a, dict) and str(a.get("result", "")).lower() == target:
                return str(a.get("text", "")), str(a.get("evidence", ""))
    return "", ""


def _verify_claim(
    claim: ExtractedClaim,
    screen_states: dict[str, dict],
    verify_template: str,
    decompose_template: str,
) -> Verdict:
    sid = _slugify(claim.target_screen)
    state = screen_states.get(sid)
    if state is None:
        return Verdict(
            claim_id=claim.id, result="uncertain", confidence=0.0,
            reasoning="No screen state captured for target screen.", evidence="",
        )

    atoms = decompose_claim(claim, decompose_template)
    sub_types = {a["sub_type"] for a in atoms}

    # Assemble evidence + decide which path(s) this claim needs.
    evidence_note = ""
    evidence_source = "text"

    needs_nav = "nav" in sub_types or claim.type == "nav_path"
    if needs_nav:
        trace_text = _format_trace(state["replay_trace"]) or _format_trace(state["discovery_trace"])
        if trace_text:
            evidence_note += f"## Navigation trace\n{trace_text}\n"
            evidence_source = "trace"
        else:
            evidence_note += ("## Navigation trace\n(No navigation trace was captured; "
                              "nav atoms cannot be confirmed.)\n")

    needs_visual = "visual" in sub_types
    use_image = bool(needs_visual and IMAGE_INPUT_ENABLED and state["screenshot"] is not None)
    if needs_visual and use_image:
        evidence_source = "image"

    result, confidence, winning_atoms, reasoning, votes_str = _self_consistent_verify(
        claim, atoms, state["description"], verify_template,
        evidence_note=evidence_note, use_image=use_image,
        screenshot_path=state["screenshot"],
    )

    failing_text, failing_evidence = _first_failing_atom(winning_atoms)
    # Headline evidence: the deciding atom's evidence, else the first atom's.
    evidence = failing_evidence
    if not evidence and winning_atoms and isinstance(winning_atoms[0], dict):
        evidence = str(winning_atoms[0].get("evidence", ""))

    return Verdict(
        claim_id=claim.id,
        result=result,
        confidence=confidence,
        reasoning=reasoning,
        evidence=evidence,
        used_image_fallback=use_image,
        failing_atom=failing_text,
        evidence_source=evidence_source,
        votes=votes_str,
    )


def run(dataset_id: str, product: str = "grafana") -> list[Verdict]:
    """Run claim verification for a dataset. Returns list of Verdicts."""
    ensure_dirs()

    claims = _load_claims(dataset_id)
    screen_states = _load_screen_states(dataset_id, product)
    verify_template = _load_template("verify_claim.txt")
    decompose_template = _load_template("decompose_claim.txt")

    verdicts: list[Verdict] = []
    for i, claim in enumerate(claims, 1):
        print(f"  [{i}/{len(claims)}] Verifying: {claim.id} ...", flush=True)
        verdict = _verify_claim(claim, screen_states, verify_template, decompose_template)
        verdicts.append(verdict)
        extra = f" via {verdict.evidence_source}" if verdict.evidence_source != "text" else ""
        print(f"    -> {verdict.result} ({verdict.votes}{extra})", flush=True)

    out_path = VERDICTS_DIR / f"{dataset_id}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump([v.model_dump() for v in verdicts], f, indent=2)
    print(f"\nWrote {len(verdicts)} verdicts to {out_path}")

    return verdicts


def evaluate(dataset_id: str) -> None:
    """Evaluate verdicts against ground truth via the canonical scorer.

    All ground-truth access and confusion-matrix logic lives in `metrics.py`
    (guard L1); this just loads the prediction outputs and prints the report.
    """
    verdict_results = metrics.load_verdict_results(dataset_id)
    if not verdict_results:
        print(f"No verdicts found for '{dataset_id}'. Run verification first.")
        return
    score = metrics.score_verdicts(verdict_results, dataset_id)
    print(metrics.format_verification(score))


if __name__ == "__main__":
    dataset = sys.argv[1] if len(sys.argv) > 1 else "grafana-p1-clean"
    prod = sys.argv[2] if len(sys.argv) > 2 else "grafana"
    run(dataset, prod)
    evaluate(dataset)

"""Phase 4: Claim Verification — verify extracted claims against captured screen states."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from pipeline.config import (
    CLAIMS_DIR,
    DESCRIPTIONS_DIR,
    MANIFEST_PATH,
    MODEL_VERIFY,
    PROMPTS_DIR,
    SCREENSHOTS_DIR,
    VERDICTS_DIR,
    ensure_dirs,
)
from pipeline.claude_runner import run_claude
from pipeline.models import ExtractedClaim, Verdict


def _slugify(screen_name: str) -> str:
    """Convert a target_screen name to a file-system-safe screen_id."""
    slug = screen_name.lower()
    slug = slug.replace(" ", "-")
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def _load_claims(dataset_id: str) -> list[ExtractedClaim]:
    path = CLAIMS_DIR / f"{dataset_id}.json"
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return [ExtractedClaim(**c) for c in raw]


def _load_screen_states() -> dict[str, tuple[str, Path | None]]:
    """Build mapping: screen_id -> (description_text, screenshot_path or None)."""
    screens: dict[str, tuple[str, Path | None]] = {}

    for desc_file in DESCRIPTIONS_DIR.glob("*.txt"):
        screen_id = desc_file.stem
        text = desc_file.read_text(encoding="utf-8")
        screenshot = SCREENSHOTS_DIR / f"{screen_id}.png"
        screens[screen_id] = (text, screenshot if screenshot.exists() else None)

    return screens


def _load_prompt_template() -> str:
    path = PROMPTS_DIR / "verify_claim.txt"
    return path.read_text(encoding="utf-8")


def _parse_verdict(response: dict, claim: ExtractedClaim, used_image: bool) -> Verdict | None:
    """Extract a Verdict from a claude_runner response."""
    if not response.get("success"):
        return None

    raw = response.get("raw", "")

    # Try parsed JSON first (from json_output mode), fall back to raw text parsing.
    data = response.get("parsed")
    if data is None:
        # Try to extract JSON from raw text.
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return None
        else:
            return None

    return Verdict(
        claim_id=data.get("claim_id", claim.id),
        result=data.get("result", "uncertain"),
        confidence=float(data.get("confidence", 0.0)),
        reasoning=data.get("reasoning", ""),
        evidence=data.get("evidence", ""),
        used_image_fallback=used_image,
    )


def _verify_claim(
    claim: ExtractedClaim,
    screen_states: dict[str, tuple[str, Path | None]],
    template: str,
) -> Verdict:
    screen_id = _slugify(claim.target_screen)

    if screen_id not in screen_states:
        return Verdict(
            claim_id=claim.id,
            result="uncertain",
            confidence=0.0,
            reasoning="No screen state captured for target screen.",
            evidence="",
        )

    description, screenshot_path = screen_states[screen_id]
    claim_json = json.dumps(claim.model_dump(), indent=2)

    # --- Text-first verification (cheap path) ---
    prompt = (
        template
        .replace("{claim_json}", claim_json)
        .replace("{screen_description}", description)
        .replace("{screenshot_note}", "")
    )
    response = run_claude(prompt, model=MODEL_VERIFY, json_output=True)
    verdict = _parse_verdict(response, claim, used_image=False)

    if verdict and verdict.result != "uncertain":
        return verdict

    # --- Image fallback (expensive path) ---
    if screenshot_path:
        prompt = (
            template
            .replace("{claim_json}", claim_json)
            .replace("{screen_description}", description)
            .replace("{screenshot_note}", "A screenshot is also attached for visual verification.")
        )
        response = run_claude(prompt, model=MODEL_VERIFY, json_output=True)
        fallback = _parse_verdict(response, claim, used_image=True)
        if fallback:
            return fallback

    # Return text-first verdict if image fallback didn't help or no screenshot.
    if verdict:
        return verdict

    return Verdict(
        claim_id=claim.id,
        result="uncertain",
        confidence=0.0,
        reasoning="Verification failed: could not parse model response.",
        evidence="",
    )


def run(dataset_id: str) -> list[Verdict]:
    """Run claim verification for a dataset. Returns list of Verdicts."""
    ensure_dirs()

    claims = _load_claims(dataset_id)
    screen_states = _load_screen_states()
    template = _load_prompt_template()

    verdicts: list[Verdict] = []
    for i, claim in enumerate(claims, 1):
        print(f"  [{i}/{len(claims)}] Verifying: {claim.id} ...", flush=True)
        verdict = _verify_claim(claim, screen_states, template)
        verdicts.append(verdict)
        print(f"    -> {verdict.result} (confidence={verdict.confidence:.2f})", flush=True)

    # Write results.
    out_path = VERDICTS_DIR / f"{dataset_id}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump([v.model_dump() for v in verdicts], f, indent=2)
    print(f"\nWrote {len(verdicts)} verdicts to {out_path}")

    return verdicts


def evaluate(dataset_id: str) -> None:
    """Evaluate verdicts against ground truth from manifest.jsonl."""
    # Load verdicts.
    verdicts_path = VERDICTS_DIR / f"{dataset_id}.json"
    with open(verdicts_path, encoding="utf-8") as f:
        verdicts_raw = json.load(f)
    verdicts_by_id = {v["claim_id"]: v for v in verdicts_raw}

    # Load ground truth from manifest.
    ground_truth: dict[str, bool] = {}
    expected_findings: list[str] = []
    is_mutated = False

    with open(MANIFEST_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if entry["id"] != dataset_id:
                continue

            is_mutated = entry.get("is_mutated", False)
            expected_findings = entry.get("expected_findings", [])
            for claim in entry.get("claims", []):
                ground_truth[claim["id"]] = claim["is_correct"]
            break

    if not ground_truth:
        print(f"No ground truth found for dataset '{dataset_id}' in manifest.")
        return

    # Compute metrics.
    total = 0
    correct = 0
    uncertain_count = 0
    false_positives = 0  # Verdict says "true" but claim is_correct=False
    false_negatives = 0  # Verdict says "false" but claim is_correct=True
    fp_claims: list[str] = []
    fn_claims: list[str] = []

    for claim_id, is_correct in ground_truth.items():
        verdict = verdicts_by_id.get(claim_id)
        if not verdict:
            continue
        total += 1
        result = verdict["result"]

        if result == "uncertain":
            uncertain_count += 1
            continue

        verdict_correct = (result == "true") == is_correct
        if verdict_correct:
            correct += 1
        elif result == "true" and not is_correct:
            false_positives += 1
            fp_claims.append(claim_id)
        elif result == "false" and is_correct:
            false_negatives += 1
            fn_claims.append(claim_id)

    decided = total - uncertain_count
    accuracy = correct / decided if decided > 0 else 0.0
    uncertain_rate = uncertain_count / total if total > 0 else 0.0

    # For clean datasets: false positive rate = FP / total clean claims.
    # For mutated datasets: false negative rate = FN / total mutated (incorrect) claims.
    total_clean = sum(1 for v in ground_truth.values() if v)
    total_mutated = sum(1 for v in ground_truth.values() if not v)

    fp_rate = false_positives / total_mutated if total_mutated > 0 else 0.0
    fn_rate = false_negatives / total_clean if total_clean > 0 else 0.0

    print(f"\n{'='*60}")
    print(f"  Evaluation: {dataset_id}")
    print(f"  Mutated: {is_mutated}")
    print(f"{'='*60}")
    print(f"  Total claims:      {total}")
    print(f"  Decided:           {decided}")
    print(f"  Correct:           {correct}")
    print(f"  Accuracy:          {accuracy:.1%}")
    print(f"  Uncertain:         {uncertain_count} ({uncertain_rate:.1%})")
    print(f"  False positives:   {false_positives} (rate: {fp_rate:.1%} of {total_mutated} mutated)")
    print(f"  False negatives:   {false_negatives} (rate: {fn_rate:.1%} of {total_clean} clean)")
    if fp_claims:
        print(f"  FP claims:         {fp_claims}")
    if fn_claims:
        print(f"  FN claims:         {fn_claims}")
    if expected_findings:
        found = [ef for ef in expected_findings if any(ef in cid for cid in fp_claims + fn_claims)]
        print(f"  Expected findings: {expected_findings}")
        print(f"  Matched findings:  {found}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    dataset = sys.argv[1] if len(sys.argv) > 1 else "grafana-p1-clean"
    run(dataset)
    evaluate(dataset)

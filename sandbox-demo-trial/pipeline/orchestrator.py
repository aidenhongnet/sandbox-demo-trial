"""End-to-end orchestrator: wires phases 1-4, runs against dataset entries, produces report."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from . import config
from .models import ExtractedClaim, DriverPlan, ScreenState, Verdict


def load_manifest_entry(dataset_id: str) -> dict:
    with open(config.MANIFEST_PATH, encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line.strip())
            if entry["id"] == dataset_id:
                return entry
    raise ValueError(f"Dataset entry '{dataset_id}' not found in manifest")


def run_pipeline(dataset_id: str, *, skip_drive: bool = False) -> dict:
    """Run the full pipeline for a single dataset entry. Returns a report dict."""
    config.ensure_dirs()
    entry = load_manifest_entry(dataset_id)
    product = entry["product"]
    page_id = entry["page_id"]
    report: dict = {"dataset_id": dataset_id, "product": product, "page_id": page_id, "phases": {}}

    # --- Phase 1: Extract ---
    print(f"\n{'='*60}")
    print(f"Phase 1: Claim Extraction — {dataset_id}")
    print(f"{'='*60}")
    t0 = time.time()
    from .extract import run as extract_run
    claims = extract_run(dataset_id, product, page_id, doc_content=entry.get("content"))
    phase1_time = time.time() - t0
    report["phases"]["extract"] = {
        "claims_extracted": len(claims),
        "time_seconds": round(phase1_time, 1),
    }
    print(f"  Extracted {len(claims)} claims in {phase1_time:.1f}s")

    # --- Phase 2: Plan ---
    print(f"\n{'='*60}")
    print(f"Phase 2: Driver Planning — {dataset_id}")
    print(f"{'='*60}")
    t0 = time.time()
    from .plan import run as plan_run
    plans = plan_run(dataset_id)
    phase2_time = time.time() - t0
    report["phases"]["plan"] = {
        "plans_generated": len(plans),
        "time_seconds": round(phase2_time, 1),
    }
    print(f"  Generated {len(plans)} driver plans in {phase2_time:.1f}s")

    # --- Phase 3: Drive ---
    if skip_drive:
        print(f"\n{'='*60}")
        print(f"Phase 3: Drive — SKIPPED (--skip-drive)")
        print(f"{'='*60}")
        screen_states = []
        report["phases"]["drive"] = {"skipped": True}
    else:
        print(f"\n{'='*60}")
        print(f"Phase 3: Autonomous Driving — {dataset_id}")
        print(f"{'='*60}")
        t0 = time.time()
        from .drive import run as drive_run
        screen_states = drive_run(dataset_id)
        phase3_time = time.time() - t0
        succeeded = sum(1 for s in screen_states if s.success)
        report["phases"]["drive"] = {
            "screens_attempted": len(screen_states),
            "screens_reached": succeeded,
            "success_rate": round(succeeded / max(len(screen_states), 1), 2),
            "time_seconds": round(phase3_time, 1),
        }
        print(f"  Drove {succeeded}/{len(screen_states)} screens in {phase3_time:.1f}s")

    # --- Phase 4: Verify ---
    print(f"\n{'='*60}")
    print(f"Phase 4: Verification — {dataset_id}")
    print(f"{'='*60}")
    t0 = time.time()
    from .verify import run as verify_run
    verdicts = verify_run(dataset_id)
    phase4_time = time.time() - t0
    true_count = sum(1 for v in verdicts if v.result == "true")
    false_count = sum(1 for v in verdicts if v.result == "false")
    uncertain_count = sum(1 for v in verdicts if v.result == "uncertain")
    fallback_count = sum(1 for v in verdicts if v.used_image_fallback)
    report["phases"]["verify"] = {
        "total_verdicts": len(verdicts),
        "true": true_count,
        "false": false_count,
        "uncertain": uncertain_count,
        "image_fallbacks": fallback_count,
        "time_seconds": round(phase4_time, 1),
    }
    print(f"  Verdicts: {true_count} true, {false_count} false, {uncertain_count} uncertain")
    print(f"  Image fallbacks: {fallback_count}")

    return report


def evaluate_against_ground_truth(dataset_id: str, report: dict) -> dict:
    """Compare pipeline results against manifest ground truth."""
    entry = load_manifest_entry(dataset_id)
    gt_claims = {c["id"]: c for c in entry["claims"]}
    expected_findings = set(entry.get("expected_findings", []))
    is_mutated = entry["is_mutated"]

    verdicts_path = config.VERDICTS_DIR / f"{dataset_id}.json"
    if not verdicts_path.exists():
        return {"error": "No verdicts found"}

    with open(verdicts_path, encoding="utf-8") as f:
        verdicts_data = json.load(f)
    verdicts = {v["claim_id"]: v for v in verdicts_data}

    # Extraction evaluation
    claims_path = config.CLAIMS_DIR / f"{dataset_id}.json"
    extraction_eval = {"recall": 0.0, "precision": 0.0, "type_accuracy": 0.0}
    if claims_path.exists():
        with open(claims_path, encoding="utf-8") as f:
            extracted = json.load(f)
        extracted_texts = {c["text"].lower().strip() for c in extracted}
        gt_texts = {c["text"].lower().strip(): c for c in entry["claims"]}

        matched = 0
        type_matches = 0
        for gt_text, gt_claim in gt_texts.items():
            for ext in extracted:
                if _text_overlap(ext["text"], gt_claim["text"]) > 0.6:
                    matched += 1
                    if ext["type"] == gt_claim["type"]:
                        type_matches += 1
                    break

        extraction_eval["recall"] = round(matched / max(len(gt_texts), 1), 2)
        extraction_eval["precision"] = round(matched / max(len(extracted), 1), 2)
        extraction_eval["type_accuracy"] = round(type_matches / max(matched, 1), 2)
        extraction_eval["gt_claims"] = len(gt_texts)
        extraction_eval["extracted_claims"] = len(extracted)
        extraction_eval["matched"] = matched

    # Verification evaluation
    correct = 0
    false_positives = 0
    false_negatives = 0
    total_evaluated = 0

    for claim_id, gt in gt_claims.items():
        if claim_id not in verdicts:
            continue
        v = verdicts[claim_id]
        total_evaluated += 1

        gt_correct = gt["is_correct"]
        verdict_says_correct = v["result"] == "true"

        if gt_correct == verdict_says_correct:
            correct += 1
        elif not gt_correct and verdict_says_correct:
            false_negatives += 1
        elif gt_correct and not verdict_says_correct:
            false_positives += 1

    verification_eval = {
        "accuracy": round(correct / max(total_evaluated, 1), 2),
        "false_positive_rate": round(false_positives / max(total_evaluated, 1), 2),
        "false_negative_rate": round(false_negatives / max(total_evaluated, 1), 2),
        "total_evaluated": total_evaluated,
    }

    if is_mutated and expected_findings:
        detected = [f for f in expected_findings if verdicts.get(f, {}).get("result") == "false"]
        verification_eval["mutation_detected"] = len(detected) == len(expected_findings)
        verification_eval["mutations_found"] = detected
        verification_eval["mutations_expected"] = list(expected_findings)

    return {
        "extraction": extraction_eval,
        "verification": verification_eval,
    }


def _text_overlap(a: str, b: str) -> float:
    """Simple word-overlap ratio for fuzzy claim matching."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    return len(intersection) / max(len(words_a), len(words_b))


def print_report(report: dict, eval_results: dict) -> None:
    """Print a formatted summary report."""
    print(f"\n{'='*60}")
    print(f"PIPELINE REPORT: {report['dataset_id']}")
    print(f"{'='*60}")

    for phase_name, phase_data in report["phases"].items():
        print(f"\n  {phase_name.upper()}:")
        for k, v in phase_data.items():
            print(f"    {k}: {v}")

    if "extraction" in eval_results:
        ext = eval_results["extraction"]
        print(f"\n  EXTRACTION EVAL:")
        print(f"    Recall: {ext.get('recall', 'N/A')}")
        print(f"    Precision: {ext.get('precision', 'N/A')}")
        print(f"    Type accuracy: {ext.get('type_accuracy', 'N/A')}")

    if "verification" in eval_results:
        ver = eval_results["verification"]
        print(f"\n  VERIFICATION EVAL:")
        print(f"    Accuracy: {ver.get('accuracy', 'N/A')}")
        print(f"    FP rate: {ver.get('false_positive_rate', 'N/A')}")
        print(f"    FN rate: {ver.get('false_negative_rate', 'N/A')}")
        if "mutation_detected" in ver:
            print(f"    Mutation detected: {ver['mutation_detected']}")
            print(f"    Mutations found: {ver.get('mutations_found', [])}")

    print(f"\n{'='*60}")


def main() -> None:
    skip_drive = "--skip-drive" in sys.argv
    dataset_ids = ["grafana-p1-clean", "grafana-p1-m1"]

    all_reports = []
    for dataset_id in dataset_ids:
        report = run_pipeline(dataset_id, skip_drive=skip_drive)
        eval_results = evaluate_against_ground_truth(dataset_id, report)
        print_report(report, eval_results)
        all_reports.append({"report": report, "evaluation": eval_results})

    output_path = config.RESULTS_DIR / "pipeline_report.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_reports, f, indent=2)
    print(f"\nFull report written to {output_path}")


if __name__ == "__main__":
    main()

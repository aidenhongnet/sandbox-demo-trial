"""End-to-end orchestrator: wires phases 1-4, runs against dataset entries, produces report.

All evaluation (confusion matrix, recall/precision, cost) is delegated to
`metrics.py` so there is exactly one definition of every number reported here.
The orchestrator reads the manifest only for the *prediction inputs* it must
forward (product, page_id, doc content) — never the ground-truth labels (L1).
"""

from __future__ import annotations

import json
import sys
import time

from . import config, metrics
from .claude_runner import COST


def load_manifest_entry(dataset_id: str) -> dict:
    with open(config.MANIFEST_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if entry["id"] == dataset_id:
                return entry
    raise ValueError(f"Dataset entry '{dataset_id}' not found in manifest")


def run_pipeline(dataset_id: str, *, skip_drive: bool = False, oracle_claims: bool = False) -> dict:
    """Run the full pipeline for a single dataset entry. Returns a report dict.

    oracle_claims: DEBUG path — seed plan/drive/verify from the ground-truth claims
    (canonical, labels stripped by metrics.py) instead of real extraction. Never
    use for headline metrics; the default is true end-to-end extraction.
    """
    config.ensure_dirs()
    entry = load_manifest_entry(dataset_id)
    product = entry["product"]
    page_id = entry["page_id"]
    report: dict = {"dataset_id": dataset_id, "product": product, "page_id": page_id, "phases": {}}

    # --- Phase 1: Extract ---
    print(f"\n{'='*60}")
    print(f"Phase 1: Claim Extraction — {dataset_id}")
    print(f"{'='*60}")
    t0, mark = time.time(), COST.mark()
    if oracle_claims:
        seeded = metrics.oracle_claims(dataset_id)
        (config.CLAIMS_DIR / f"{dataset_id}.json").write_text(
            json.dumps(seeded, indent=2), encoding="utf-8")
        claims = seeded
        report["phases"]["extract"] = {
            "claims_extracted": len(claims), "oracle_seeded": True,
            "time_seconds": round(time.time() - t0, 1), "cost_usd": 0.0,
        }
        print(f"  [oracle] Seeded {len(claims)} GT claims (DEBUG — not a real extraction)")
    else:
        from .extract import run as extract_run
        # Only entry["content"] crosses into the (GT-blind) extractor — never the entry (L1).
        claims = extract_run(dataset_id, product, page_id, doc_content=entry.get("content"))
        report["phases"]["extract"] = {
            "claims_extracted": len(claims),
            "time_seconds": round(time.time() - t0, 1),
            "cost_usd": round(COST.since(mark), 4),
        }
        print(f"  Extracted {len(claims)} claims in {report['phases']['extract']['time_seconds']}s")

    # --- Phase 2: Plan ---
    print(f"\n{'='*60}")
    print(f"Phase 2: Driver Planning — {dataset_id}")
    print(f"{'='*60}")
    t0, mark = time.time(), COST.mark()
    from .plan import run as plan_run
    plans = plan_run(dataset_id, product)
    report["phases"]["plan"] = {
        "plans_generated": len(plans),
        "time_seconds": round(time.time() - t0, 1),
        "cost_usd": round(COST.since(mark), 4),
    }
    print(f"  Generated {len(plans)} driver plans in {report['phases']['plan']['time_seconds']}s")

    # --- Phase 3: Drive ---
    if skip_drive:
        print(f"\n{'='*60}")
        print(f"Phase 3: Drive — SKIPPED (--skip-drive)")
        print(f"{'='*60}")
        report["phases"]["drive"] = {"skipped": True, "cost_usd": 0.0}
    else:
        print(f"\n{'='*60}")
        print(f"Phase 3: Autonomous Driving — {dataset_id}")
        print(f"{'='*60}")
        t0, mark = time.time(), COST.mark()
        from .drive import run as drive_run
        screen_states = drive_run(dataset_id, product)
        succeeded = sum(1 for s in screen_states if s.success)
        report["phases"]["drive"] = {
            "screens_attempted": len(screen_states),
            "screens_reached": succeeded,
            "success_rate": round(succeeded / max(len(screen_states), 1), 2),
            "time_seconds": round(time.time() - t0, 1),
            "cost_usd": round(COST.since(mark), 4),
        }
        print(f"  Drove {succeeded}/{len(screen_states)} screens in {report['phases']['drive']['time_seconds']}s")

    # --- Phase 4: Verify ---
    print(f"\n{'='*60}")
    print(f"Phase 4: Verification — {dataset_id}")
    print(f"{'='*60}")
    t0, mark = time.time(), COST.mark()
    from .verify import run as verify_run
    verdicts = verify_run(dataset_id, product)
    report["phases"]["verify"] = {
        "total_verdicts": len(verdicts),
        "true": sum(1 for v in verdicts if v.result == "true"),
        "false": sum(1 for v in verdicts if v.result == "false"),
        "uncertain": sum(1 for v in verdicts if v.result == "uncertain"),
        "image_fallbacks": sum(1 for v in verdicts if v.used_image_fallback),
        "time_seconds": round(time.time() - t0, 1),
        "cost_usd": round(COST.since(mark), 4),
    }
    v = report["phases"]["verify"]
    print(f"  Verdicts: {v['true']} true, {v['false']} false, {v['uncertain']} uncertain")
    print(f"  Image fallbacks: {v['image_fallbacks']}")

    report["cost_usd_total"] = round(
        sum(p.get("cost_usd", 0.0) for p in report["phases"].values()), 4
    )
    return report


def evaluate_against_ground_truth(dataset_id: str, *, oracle: bool = False) -> dict:
    """Score pipeline outputs against ground truth using the canonical metrics.

    For a real (non-oracle) E2E run, extracted-claim IDs do not line up with GT
    IDs, so we ask metrics for a semantic alignment (open item #4) and pass it to
    `score_verdicts`. The oracle path keeps identity alignment (IDs already match).
    All ground-truth access stays inside metrics.py (L1).
    """
    result: dict = {}
    alignment: dict[str, str] | None = None

    if oracle:
        # Claims were GT-seeded; extraction recall is trivially ~1.0 and meaningless.
        result["extraction"] = {"oracle_seeded": True, "note": "extraction bypassed (debug)"}
    else:
        extracted = metrics.load_extracted_claims(dataset_id)
        if extracted:
            result["extraction"] = metrics.score_extraction(extracted, dataset_id).as_dict()
            alignment = metrics.alignment_for(dataset_id, extracted)

    verdict_results = metrics.load_verdict_results(dataset_id)
    if verdict_results:
        result["verification"] = metrics.score_verdicts(
            verdict_results, dataset_id, alignment=alignment
        ).as_dict()
    else:
        result["verification"] = {"error": "No verdicts found"}

    return result


def print_report(report: dict, eval_results: dict) -> None:
    """Print a formatted summary report."""
    print(f"\n{'='*60}")
    print(f"PIPELINE REPORT: {report['dataset_id']}")
    print(f"{'='*60}")

    for phase_name, phase_data in report["phases"].items():
        print(f"\n  {phase_name.upper()}:")
        for k, val in phase_data.items():
            print(f"    {k}: {val}")

    print(f"\n  TOTAL COST: ${report.get('cost_usd_total', 0.0)}")

    if "extraction" in eval_results:
        ext = eval_results["extraction"]
        print(f"\n  EXTRACTION EVAL:")
        if ext.get("oracle_seeded"):
            print(f"    (oracle-seeded debug run — extraction not measured)")
        else:
            print(f"    Recall: {ext.get('recall')}  Precision: {ext.get('precision')}")
            print(f"    Type accuracy: {ext.get('type_accuracy')}  Attribution: {ext.get('attribution_accuracy')}")

    ver = eval_results.get("verification", {})
    print(f"\n  VERIFICATION EVAL (detection framing):")
    if "error" in ver:
        print(f"    {ver['error']}")
    else:
        print(f"    TP {ver['tp']}  FP {ver['fp']}  FN {ver['fn']}  TN {ver['tn']}  "
              f"uncertain {ver['uncertain']}")
        print(f"    Coverage: {ver['coverage']}  Accuracy: {ver['accuracy']}  "
              f"Recall: {ver['recall']}")
        if "mutation_detected" in ver:
            print(f"    Mutation detected: {ver['mutation_detected']}  "
                  f"(expected {ver.get('expected_findings')}, detected {ver.get('detected')})")

    print(f"\n{'='*60}")


def _select_dataset_ids(argv: list[str]) -> list[str]:
    """Resolve which dataset entries to run.

    Reads the manifest only for prediction inputs (entry ids/product) — never GT
    labels (L1). `--product <name>` selects every entry of that product;
    `--dataset <id>` (repeatable) selects explicit entries; default keeps the
    original two grafana-p1 entries so existing invocations are unchanged.
    """
    explicit = [argv[i + 1] for i, a in enumerate(argv)
                if a == "--dataset" and i + 1 < len(argv)]
    if explicit:
        return explicit
    product = next((argv[i + 1] for i, a in enumerate(argv)
                    if a == "--product" and i + 1 < len(argv)), None)
    if product:
        from dataset.loader import load, filter_by
        return [e["id"] for e in filter_by(load(), product=product)]
    return ["grafana-p1-clean", "grafana-p1-m1"]


def main() -> None:
    skip_drive = "--skip-drive" in sys.argv
    oracle = "--oracle-claims" in sys.argv  # DEBUG: seed claims from GT (not headline)
    dataset_ids = _select_dataset_ids(sys.argv)

    all_reports = []
    for dataset_id in dataset_ids:
        try:
            report = run_pipeline(dataset_id, skip_drive=skip_drive, oracle_claims=oracle)
            eval_results = evaluate_against_ground_truth(dataset_id, oracle=oracle)
            print_report(report, eval_results)
            all_reports.append({"report": report, "evaluation": eval_results})
        except Exception as e:  # one dataset's hard failure must not nuke the rest
            import traceback
            print(f"\nERROR: pipeline failed for {dataset_id}: {e}")
            traceback.print_exc()
            all_reports.append(
                {"report": {"dataset_id": dataset_id, "error": str(e)}, "evaluation": {}}
            )

    # Cross-check captured cost (authoritative, billed) against the rate card.
    captured = round(COST.total, 4)
    estimated = round(COST.estimated_total(), 4)
    print(f"\nTotal captured cost: ${captured}  (rate-card cross-check: ${estimated})")

    output_path = config.RESULTS_DIR / "pipeline_report.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_reports, f, indent=2)
    print(f"\nFull report written to {output_path}")


if __name__ == "__main__":
    main()

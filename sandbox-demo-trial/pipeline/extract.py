"""Phase 1: Claim Extraction — extract verifiable claims from product documentation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pipeline.config import (
    CLAIMS_DIR,
    MANIFEST_PATH,
    MODEL_EXTRACT,
    PROMPTS_DIR,
    SOURCES_DIR,
    ensure_dirs,
)
from pipeline.claude_runner import run_claude
from pipeline.models import ExtractedClaim

VALID_TYPES = {"nav_path", "ui_element", "field_value", "behavior", "visual_state"}


def _load_prompt_template() -> str:
    path = PROMPTS_DIR / "extract_claims.txt"
    return path.read_text(encoding="utf-8")


def _load_source_doc(product: str, page_id: str) -> str:
    """Load the source document, trying .md first then .adoc.

    Handles page_id formats like "grafana-p1" where the source file is "p1_create_dashboard.md".
    """
    product_dir = SOURCES_DIR / product
    for ext in (".md", ".adoc"):
        path = product_dir / f"{page_id}{ext}"
        if path.exists():
            return path.read_text(encoding="utf-8")
    # Fallback: extract page number prefix (e.g. "grafana-p1" -> "p1") and glob
    parts = page_id.split("-")
    for part in reversed(parts):
        if part.startswith("p") and part[1:].isdigit():
            for ext in (".md", ".adoc"):
                matches = sorted(product_dir.glob(f"{part}_*{ext}"))
                if matches:
                    return matches[0].read_text(encoding="utf-8")
            break
    raise FileNotFoundError(
        f"No source doc found for product={product}, page_id={page_id} "
        f"in {product_dir}"
    )


def _parse_claims(raw_parsed: list | dict | None) -> list[dict]:
    """Extract the claims list from the parsed JSON response."""
    if isinstance(raw_parsed, list):
        return raw_parsed
    if isinstance(raw_parsed, dict):
        # Handle wrapped responses like {"claims": [...]} or {"result": [...]}
        for key in ("claims", "result", "results", "extracted_claims"):
            if key in raw_parsed and isinstance(raw_parsed[key], list):
                return raw_parsed[key]
        # If it's a single claim dict, wrap it
        if "text" in raw_parsed:
            return [raw_parsed]
    return []


def _postprocess(
    claims_raw: list[dict], page_id: str
) -> list[ExtractedClaim]:
    """Assign IDs, deduplicate by text, validate types."""
    seen_texts: set[str] = set()
    result: list[ExtractedClaim] = []
    counter = 1

    for item in claims_raw:
        # Skip if missing required field
        text = item.get("text", "").strip()
        if not text:
            continue

        # Deduplicate by normalized text
        text_lower = text.lower()
        if text_lower in seen_texts:
            continue
        seen_texts.add(text_lower)

        # Validate and coerce type
        claim_type = item.get("type", "behavior")
        if claim_type not in VALID_TYPES:
            claim_type = "behavior"

        claim = ExtractedClaim(
            id=f"{page_id}-c{counter}",
            text=text,
            type=claim_type,
            target_screen=item.get("target_screen", ""),
            line_number=item.get("line_number", 0),
        )
        result.append(claim)
        counter += 1

    return result


def run(
    dataset_id: str,
    product: str,
    page_id: str,
    doc_content: str | None = None,
) -> list[ExtractedClaim]:
    """Extract claims from a documentation page.

    Args:
        doc_content: If provided, use this instead of loading from source file.
                     Required for mutated dataset entries.
    """
    ensure_dirs()

    if doc_content is None:
        doc_content = _load_source_doc(product, page_id)
    template = _load_prompt_template()
    prompt = template.replace("{doc_content}", doc_content)

    print(f"Extracting claims for {dataset_id} (model={MODEL_EXTRACT})...")
    response = run_claude(prompt, model=MODEL_EXTRACT, json_output=True)

    if not response["success"]:
        print(f"ERROR: Claude call failed: {response.get('error', 'unknown')}")
        return []

    if response.get("parse_error"):
        print(f"WARNING: {response['parse_error']}")
        print(f"Raw output (first 500 chars): {response['raw'][:500]}")
        return []

    raw_claims = _parse_claims(response.get("parsed"))
    if not raw_claims:
        print("WARNING: No claims extracted from response.")
        return []

    claims = _postprocess(raw_claims, page_id)

    # Write results
    out_path = CLAIMS_DIR / f"{dataset_id}.json"
    out_path.write_text(
        json.dumps([c.model_dump() for c in claims], indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {len(claims)} claims to {out_path}")

    return claims


def evaluate(dataset_id: str) -> None:
    """Evaluate extracted claims against manifest ground truth.

    Computes recall, precision, and type accuracy. Prints a summary.
    """
    # Load extracted claims
    claims_path = CLAIMS_DIR / f"{dataset_id}.json"
    if not claims_path.exists():
        print(f"ERROR: No extracted claims at {claims_path}. Run extraction first.")
        return

    extracted = json.loads(claims_path.read_text(encoding="utf-8"))
    extracted_texts = {c["text"].strip().lower() for c in extracted}
    extracted_by_text = {c["text"].strip().lower(): c for c in extracted}

    # Load ground truth from manifest
    ground_truth = None
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if entry["id"] == dataset_id:
                ground_truth = entry.get("claims", [])
                break

    if ground_truth is None:
        print(f"ERROR: Dataset '{dataset_id}' not found in manifest.")
        return

    gt_texts = {c["text"].strip().lower() for c in ground_truth}
    gt_by_text = {c["text"].strip().lower(): c for c in ground_truth}

    # Recall: how many ground truth claims are covered by extracted claims
    # Use fuzzy containment: GT claim is "matched" if any extracted claim
    # contains its key content (exact match on lowered text)
    matched_gt = extracted_texts & gt_texts
    recall = len(matched_gt) / len(gt_texts) if gt_texts else 0.0

    # Precision: how many extracted claims match a ground truth claim
    matched_ext = extracted_texts & gt_texts
    precision = len(matched_ext) / len(extracted_texts) if extracted_texts else 0.0

    # Type accuracy: among matched claims, how many have the correct type
    type_correct = 0
    for text_lower in matched_gt:
        if extracted_by_text[text_lower]["type"] == gt_by_text[text_lower]["type"]:
            type_correct += 1
    type_accuracy = type_correct / len(matched_gt) if matched_gt else 0.0

    # Print summary
    print(f"\n{'='*60}")
    print(f"Evaluation: {dataset_id}")
    print(f"{'='*60}")
    print(f"Ground truth claims : {len(gt_texts)}")
    print(f"Extracted claims    : {len(extracted_texts)}")
    print(f"Matched             : {len(matched_gt)}")
    print(f"Recall              : {recall:.1%}")
    print(f"Precision           : {precision:.1%}")
    print(f"Type accuracy       : {type_accuracy:.1%}")
    print(f"{'='*60}")

    # Show unmatched ground truth (missed)
    missed = gt_texts - matched_gt
    if missed:
        print(f"\nMissed ground truth claims ({len(missed)}):")
        for i, text in enumerate(sorted(missed), 1):
            gt_claim = gt_by_text[text]
            print(f"  {i}. [{gt_claim['type']}] {gt_claim['text'][:100]}")

    # Show extra extracted claims (not in ground truth)
    extra = extracted_texts - matched_ext
    if extra:
        print(f"\nExtra extracted claims ({len(extra)}):")
        for i, text in enumerate(sorted(extra), 1):
            ext_claim = extracted_by_text[text]
            print(f"  {i}. [{ext_claim['type']}] {ext_claim['text'][:100]}")


if __name__ == "__main__":
    dataset = sys.argv[1] if len(sys.argv) > 1 else "grafana-p1-clean"
    product_name = sys.argv[2] if len(sys.argv) > 2 else "grafana"
    page = sys.argv[3] if len(sys.argv) > 3 else "p1_create_dashboard"

    claims = run(dataset, product_name, page)
    if claims:
        print(f"\nExtracted {len(claims)} claims. Running evaluation...")
        evaluate(dataset)

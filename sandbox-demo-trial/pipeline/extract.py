"""Phase 1: Claim Extraction — extract verifiable claims from product documentation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pipeline import metrics, ontology
from pipeline.config import (
    CLAIMS_DIR,
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
    claims_raw: list[dict], page_id: str, dedup_threshold: float = 0.8
) -> list[ExtractedClaim]:
    """Assign IDs, validate types, and collapse duplicates.

    Beyond exact-text dedup, a semantic pass drops near-paraphrases (word overlap
    >= dedup_threshold with an already-kept claim) so extraction lands near human
    density (~25-40) instead of over-producing (Fix 6).
    """
    seen_texts: set[str] = set()
    kept_texts: list[str] = []
    result: list[ExtractedClaim] = []
    counter = 1

    for item in claims_raw:
        # Skip if missing required field
        text = item.get("text", "").strip()
        if not text:
            continue

        # Exact dedup, then semantic (near-paraphrase) dedup.
        text_lower = text.lower()
        if text_lower in seen_texts:
            continue
        if any(metrics.text_overlap(text, kt) >= dedup_threshold for kt in kept_texts):
            continue
        seen_texts.add(text_lower)
        kept_texts.append(text)

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
    normalize_screens: bool = True,
) -> list[ExtractedClaim]:
    """Extract claims from a documentation page.

    Args:
        doc_content: If provided, use this instead of loading from source file.
                     Required for mutated dataset entries.
        normalize_screens: Canonicalize each claim's target_screen to the
                     product-derived ontology (Fix 6 / L5). Disable only for
                     debugging raw extractor output.
    """
    ensure_dirs()

    if doc_content is None:
        doc_content = _load_source_doc(product, page_id)
    template = _load_prompt_template()
    prompt = template.replace("{doc_content}", doc_content)

    print(f"Extracting claims for {dataset_id} (model={MODEL_EXTRACT})...")
    # The extractor LLM occasionally returns an empty / unparseable batch on one
    # call even though the doc has plenty of claims (run-to-run formatting variance).
    # A single such blip would silently drop a whole dataset entry from the run, so
    # retry a few times before giving up. (No ground-truth access here — L1-clean.)
    raw_claims: list[dict] = []
    last_err = ""
    for attempt in range(1, 4):
        response = run_claude(prompt, model=MODEL_EXTRACT, json_output=True)
        if not response["success"]:
            last_err = f"call failed: {response.get('error', 'unknown')}"
        elif response.get("parse_error"):
            last_err = f"parse error: {response['parse_error']}"
        else:
            raw_claims = _parse_claims(response.get("parsed"))
            if raw_claims:
                break
            last_err = "no claims parsed from response"
        print(f"  extraction attempt {attempt}/3 yielded nothing ({last_err}); "
              f"{'retrying' if attempt < 3 else 'giving up'}")
    if not raw_claims:
        print(f"WARNING: No claims extracted for {dataset_id} after retries ({last_err}).")
        return []

    claims = _postprocess(raw_claims, page_id)

    # Canonicalize target_screen to the product-derived ontology (L5) as a
    # separate post-step — the extractor itself never sees the screen list.
    if normalize_screens:
        for c in claims:
            c.target_screen = ontology.normalize(c.target_screen, product)

    # Write results
    out_path = CLAIMS_DIR / f"{dataset_id}.json"
    out_path.write_text(
        json.dumps([c.model_dump() for c in claims], indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {len(claims)} claims to {out_path}")

    return claims


def evaluate(dataset_id: str) -> None:
    """Evaluate extracted claims against ground truth via the canonical scorer.

    Ground-truth access and the (shared, fuzzy) matcher live in `metrics.py`
    (guard L1). The previous exact lowercased set-intersection reported ~0%
    recall by construction — an LLM paraphrase never matches GT verbatim.
    """
    extracted = metrics.load_extracted_claims(dataset_id)
    if not extracted:
        print(f"ERROR: No extracted claims for '{dataset_id}'. Run extraction first.")
        return

    score = metrics.score_extraction(extracted, dataset_id)
    print(metrics.format_extraction(score))

    if score.missed:
        print(f"\nMissed ground truth claims ({len(score.missed)}):")
        for i, text in enumerate(score.missed, 1):
            print(f"  {i}. {text[:100]}")


if __name__ == "__main__":
    dataset = sys.argv[1] if len(sys.argv) > 1 else "grafana-p1-clean"
    product_name = sys.argv[2] if len(sys.argv) > 2 else "grafana"
    page = sys.argv[3] if len(sys.argv) > 3 else "p1_create_dashboard"

    claims = run(dataset, product_name, page)
    if claims:
        print(f"\nExtracted {len(claims)} claims. Running evaluation...")
        evaluate(dataset)

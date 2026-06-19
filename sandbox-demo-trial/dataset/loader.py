from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .schema import DatasetEntry

MANIFEST_PATH = Path(__file__).parent / "manifest.jsonl"

VALID_PRODUCTS = {"grafana", "keycloak", "netbox"}
VALID_PAGE_TYPES = {"procedural", "reference", "descriptive"}
VALID_MUTATION_TYPES = {"M1", "M2", "M3", "M4", "M5", "M6", "M7"}
VALID_CLAIM_TYPES = {"nav_path", "ui_element", "field_value", "behavior", "visual_state"}
VALID_DOC_FORMATS = {"markdown", "asciidoc"}


def load(path: Path | None = None) -> list[DatasetEntry]:
    """Load all entries from manifest.jsonl."""
    p = path or MANIFEST_PATH
    entries: list[DatasetEntry] = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def filter_by(
    entries: list[DatasetEntry],
    product: str | None = None,
    page_type: str | None = None,
    mutation_type: str | None = None,
    is_mutated: bool | None = None,
) -> list[DatasetEntry]:
    """Filter entries by any combination of criteria."""
    result = entries
    if product is not None:
        result = [e for e in result if e["product"] == product]
    if page_type is not None:
        result = [e for e in result if e["page_type"] == page_type]
    if is_mutated is not None:
        result = [e for e in result if e["is_mutated"] == is_mutated]
    if mutation_type is not None:
        result = [
            e for e in result
            if e["mutation"] is not None and e["mutation"]["type"] == mutation_type
        ]
    return result


def stats(entries: list[DatasetEntry]) -> dict:
    """Return counts by product, page_type, mutation_type, claim_type."""
    product_counts: Counter[str] = Counter()
    page_type_counts: Counter[str] = Counter()
    mutation_type_counts: Counter[str] = Counter()
    claim_type_counts: Counter[str] = Counter()
    clean_count = 0
    mutated_count = 0
    total_claims = 0

    for e in entries:
        product_counts[e["product"]] += 1
        page_type_counts[e["page_type"]] += 1
        if e["is_mutated"]:
            mutated_count += 1
            if e["mutation"]:
                mutation_type_counts[e["mutation"]["type"]] += 1
        else:
            clean_count += 1
        total_claims += len(e["claims"])
        for c in e["claims"]:
            claim_type_counts[c["type"]] += 1

    return {
        "total": len(entries),
        "clean": clean_count,
        "mutated": mutated_count,
        "by_product": dict(product_counts),
        "by_page_type": dict(page_type_counts),
        "by_mutation_type": dict(mutation_type_counts),
        "by_claim_type": dict(claim_type_counts),
        "total_claims": total_claims,
    }


def validate(entries: list[DatasetEntry]) -> list[str]:
    """Validate all entries against schema. Return list of error strings (empty = valid)."""
    errors: list[str] = []
    seen_ids: set[str] = set()

    for i, e in enumerate(entries):
        eid = e.get("id", f"<missing-id-at-index-{i}>")

        if eid in seen_ids:
            errors.append(f"Duplicate entry ID: {eid}")
        seen_ids.add(eid)

        if e.get("product") not in VALID_PRODUCTS:
            errors.append(f"{eid}: invalid product '{e.get('product')}'")
        if e.get("page_type") not in VALID_PAGE_TYPES:
            errors.append(f"{eid}: invalid page_type '{e.get('page_type')}'")
        if e.get("doc_format") not in VALID_DOC_FORMATS:
            errors.append(f"{eid}: invalid doc_format '{e.get('doc_format')}'")

        # Version + label provenance (Fix 1 / L6). Lenient: only entries that
        # declare a product_version are checked, so the un-migrated remainder of
        # the dataset stays valid. When declared, provenance must accompany it.
        pv = e.get("product_version")
        if pv is not None:
            if not isinstance(pv, str) or not pv.strip():
                errors.append(f"{eid}: product_version must be a non-empty string")
            if not e.get("labeled_against_version"):
                errors.append(f"{eid}: has product_version but missing labeled_against_version (L6)")
            if not e.get("labeled_by"):
                errors.append(f"{eid}: has product_version but missing labeled_by (L6)")

        if not e.get("content") or len(e.get("content", "")) < 100:
            errors.append(f"{eid}: content missing or too short (<100 chars)")

        claims = e.get("claims", [])
        if len(claims) < 5:
            errors.append(f"{eid}: fewer than 5 claims ({len(claims)})")

        claim_ids_in_page: set[str] = set()
        for c in claims:
            cid = c.get("id", "")
            if cid in claim_ids_in_page:
                errors.append(f"{eid}: duplicate claim ID {cid}")
            claim_ids_in_page.add(cid)
            if c.get("type") not in VALID_CLAIM_TYPES:
                errors.append(f"{eid}: claim {cid} has invalid type '{c.get('type')}'")

        # is_correct is INDEPENDENT of is_mutated: a claim may be is_correct=false
        # on a CLEAN doc when the real documentation drifts from the deployed
        # product (the mission's premise). Any false claim that is NOT a mutation
        # finding is a "natural discrepancy" and must carry per-claim provenance (L6).
        incorrect = {c["id"] for c in claims if not c.get("is_correct")}
        expected_set = set(e.get("expected_findings", []))

        if e.get("is_mutated"):
            mut = e.get("mutation")
            if not mut:
                errors.append(f"{eid}: is_mutated=true but mutation is null")
            else:
                if mut.get("type") not in VALID_MUTATION_TYPES:
                    errors.append(f"{eid}: invalid mutation type '{mut.get('type')}'")
                if not mut.get("original_text"):
                    errors.append(f"{eid}: mutation missing original_text")
                if not mut.get("mutated_text"):
                    errors.append(f"{eid}: mutation missing mutated_text")
                if mut.get("original_text") == mut.get("mutated_text"):
                    errors.append(f"{eid}: mutation original_text == mutated_text")
                affected = set(mut.get("affected_claim_ids", []))
                if affected != expected_set:
                    errors.append(
                        f"{eid}: affected_claim_ids {affected} != expected_findings {expected_set}"
                    )
            # Every expected finding must be labeled is_correct=false; additional
            # false claims (natural discrepancies) are allowed beyond them.
            missing = expected_set - incorrect
            if missing:
                errors.append(f"{eid}: expected_findings {missing} not marked is_correct=false")
        else:
            if e.get("mutation") is not None:
                errors.append(f"{eid}: is_mutated=false but mutation is not null")
            if e.get("expected_findings"):
                errors.append(f"{eid}: clean entry has non-empty expected_findings")

        # Provenance discipline (L6): a false claim that is not a mutation finding
        # is a natural doc-vs-product discrepancy and must be justified.
        natural_false = incorrect - expected_set
        prov = {c["id"]: c.get("provenance") for c in claims}
        for cid in sorted(natural_false):
            if not prov.get(cid):
                errors.append(
                    f"{eid}: claim {cid} is_correct=false (natural discrepancy) but has no provenance (L6)"
                )

    return errors

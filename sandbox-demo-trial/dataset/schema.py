from __future__ import annotations
from typing import TypedDict, Literal, NotRequired

ClaimType = Literal["nav_path", "ui_element", "field_value", "behavior", "visual_state"]
MutationType = Literal["M1", "M2", "M3", "M4", "M5", "M6", "M7"]
Product = Literal["grafana", "keycloak", "netbox"]
PageType = Literal["procedural", "reference", "descriptive"]
DocFormat = Literal["markdown", "asciidoc"]


class MutationLocation(TypedDict):
    line_start: int
    line_end: int


class Mutation(TypedDict):
    type: MutationType
    name: str
    description: str
    original_text: str
    mutated_text: str
    location: MutationLocation
    affected_claim_ids: list[str]


class Claim(TypedDict):
    id: str
    text: str
    type: ClaimType
    target_screen: str
    is_correct: bool
    line_number: int
    # Label provenance (L6): for a claim whose is_correct=False reflects a real
    # doc-vs-deployed-product discrepancy (not an injected mutation), the concrete
    # evidence. Read only by loader.validate + metrics.py; never by prediction modules.
    provenance: NotRequired[str]


class DatasetEntry(TypedDict):
    id: str
    product: Product
    # Deployed==labeled version (Fix 1): the exact product build the ground truth
    # was labeled against. drive.py refuses to run on a version mismatch. Must
    # equal pipeline.config.PRODUCT_VERSION (the single source of truth).
    # NotRequired only while the broader dataset is migrated; in scope for grafana-p1.
    product_version: NotRequired[str]
    page_id: str
    page_type: PageType
    page_title: str
    source_url: str
    doc_format: DocFormat
    content: str
    is_mutated: bool
    mutation: Mutation | None
    claims: list[Claim]
    expected_findings: list[str]
    # Label provenance (L6): the labels are produced independently of the
    # verification model, and the verifier never sees these fields (L1).
    labeled_against_version: NotRequired[str]
    labeled_by: NotRequired[str]

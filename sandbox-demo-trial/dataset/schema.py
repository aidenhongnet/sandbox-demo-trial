from __future__ import annotations
from typing import TypedDict, Literal

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


class DatasetEntry(TypedDict):
    id: str
    product: Product
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

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ExtractedClaim(BaseModel):
    id: str = ""
    text: str
    type: Literal["nav_path", "ui_element", "field_value", "behavior", "visual_state"]
    target_screen: str
    line_number: int


class DriverPlan(BaseModel):
    screen_id: str
    starting_url: str
    goal: str
    navigation_hints: list[str]
    what_to_capture: str
    preconditions: list[str]
    claim_ids: list[str]
    parent_screen_id: str | None = None


class NavigationStep(BaseModel):
    """One observed action in a navigation trace (Fix 2).

    For Pass A (discovery) this records the route actually taken; for Pass B
    (procedure replay) `control_present` records whether each documented control
    actually existed when the documented step was attempted.
    """

    step: int
    action: str                       # navigate | click | type | select | ...
    target_label: str = ""            # the visible label/control acted on
    resulting_url: str = ""
    resulting_title: str = ""
    control_present: bool | None = None  # Pass B: did the named control exist?
    snapshot_digest: str = ""         # short marker of the resulting DOM/snapshot
    note: str = ""


class NavigationTrace(BaseModel):
    screen_id: str
    pass_type: str = "discovery"      # "discovery" (Pass A) | "replay" (Pass B)
    product_version: str = ""
    fixture_id: str = ""
    steps: list[NavigationStep] = []
    final_url: str = ""
    final_title: str = ""


class ScreenState(BaseModel):
    screen_id: str
    screenshot_path: str
    text_description: str
    url: str
    timestamp: str
    navigation_log_path: str
    success: bool
    # Path to the captured NavigationTrace JSON (Fix 2). Empty when no trace was
    # captured (e.g. cache miss / unsupported stream-json with no authored trace).
    navigation_trace_path: str = ""


class Verdict(BaseModel):
    claim_id: str
    result: Literal["true", "false", "uncertain"]
    confidence: float
    reasoning: str
    evidence: str
    used_image_fallback: bool = False
    # Fix 3: the specific atom that drove a FALSE/UNCERTAIN, surfaced for the
    # human reviewer instead of a blunt whole-claim verdict.
    failing_atom: str = ""
    # Where the deciding evidence came from: "text" | "image" | "trace".
    evidence_source: str = "text"
    # Confidence is the self-consistency vote fraction, not the model's self-report.
    votes: str = ""

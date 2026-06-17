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


class ScreenState(BaseModel):
    screen_id: str
    screenshot_path: str
    text_description: str
    url: str
    timestamp: str
    navigation_log_path: str
    success: bool


class Verdict(BaseModel):
    claim_id: str
    result: Literal["true", "false", "uncertain"]
    confidence: float
    reasoning: str
    evidence: str
    used_image_fallback: bool = False

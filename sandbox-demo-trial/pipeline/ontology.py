"""Product-derived screen ontology + normalization (Fix 6 / leakage guard L5).

The extractor stays ground-truth-blind. Extracted `target_screen` strings are
normalized to a product-derived ontology as a SEPARATE post-step here — never by
feeding the extractor the manifest's screen names, which would make recall and
attribution circular and inflated. The ontology's source is the product's own UI
structure (`fixtures/<product>/screen_ontology.json`), not `manifest.jsonl`.

This module is product-parametric: every public function takes a `product` and
loads that product's ontology (lru-cached per product). The ontology doubles as
the navigation dependency graph — each screen's `parent` field is the single
per-product source for plan.py's depth ordering (see `deps`).
"""

from __future__ import annotations

import json
from functools import lru_cache

from pipeline import metrics
from pipeline.config import spec


@lru_cache(maxsize=None)
def _screens(product: str = "grafana") -> list[dict]:
    path = spec(product).ontology_path
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("screens", [])


def canonical_names(product: str = "grafana") -> list[str]:
    return [s["name"] for s in _screens(product)]


def deps(product: str = "grafana") -> dict[str, str | None]:
    """Navigation dependency graph derived from the ontology's `parent` field.

    Returns {screen_name -> parent_name}. This replaces plan.py's hand-maintained
    per-page dependency map: the ontology already encodes every parent link, so it
    is the one per-product artifact that drives both screen grouping and depth
    ordering. A screen absent from the ontology defaults to depth 0 (root).
    """
    return {s["name"]: s.get("parent") for s in _screens(product)}


def normalize(screen_name: str, product: str = "grafana", threshold: float = 0.3) -> str:
    """Map an arbitrary screen name to the best-matching canonical screen.

    Scores each ontology entry by word overlap against its name + id + aliases,
    with a containment bonus. Returns the original string unchanged if nothing
    clears `threshold`, so a genuinely new screen is preserved rather than
    silently mis-attributed to the wrong canonical screen.
    """
    if not screen_name:
        return screen_name

    sn = screen_name.lower()
    best_name, best_score = screen_name, threshold
    for s in _screens(product):
        candidates = [s["name"], s["id"].replace("-", " "), *s.get("aliases", [])]
        score = max((metrics.text_overlap(screen_name, c) for c in candidates), default=0.0)
        if any(c.lower() in sn or sn in c.lower() for c in candidates):
            score = max(score, 0.6)
        if score > best_score:
            best_score, best_name = score, s["name"]
    return best_name

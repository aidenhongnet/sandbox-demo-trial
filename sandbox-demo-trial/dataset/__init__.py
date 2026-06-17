"""Documentation quality evaluation dataset — 102 entries (15 clean + 87 mutated)."""

from .loader import load, filter_by, stats, validate

__all__ = ["load", "filter_by", "stats", "validate"]

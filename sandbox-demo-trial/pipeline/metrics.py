"""Canonical evaluation metrics — the single source of truth for scoring.

**Leakage guard L1.** This is the ONLY pipeline module permitted to read the
ground-truth fields (`is_correct`, `expected_findings`, `mutation`) from the
manifest. The prediction modules — `extract`/`plan`/`drive`/`verify` `.run()` —
must stay blind to those fields and must never import `_load_ground_truth`. The
import-isolation test in `tests/test_leakage_guards.py` enforces this.

It owns, in one place:
  * the canonical confusion matrix in **detection framing** — a *positive* is a
    contradiction present (`is_correct == False`), so a false negative is a
    *missed contradiction*, the costly error per MISSION.md;
  * `uncertain` as a first-class abstention bucket, never folded into FP/FN,
    reported alongside a `coverage = decided / total` metric;
  * the shared fuzzy text matcher used by every recall/precision/attribution
    computation (lifted out of `orchestrator._text_overlap`); and
  * the model rate card, for cross-checking captured cost against token usage.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import config

# Per-dataset cache for the semantic claim matcher (computed once, reused by both
# extraction scoring and E2E verdict alignment).
MATCH_CACHE_DIR = config.RESULTS_DIR / "_match_cache"

# Model alias -> (USD per 1M input tokens, USD per 1M output tokens).
# Haiku 4.5 $1/$5, Sonnet 4.6 $3/$15, Opus 4.8 $5/$25.
RATE_CARD: dict[str, tuple[float, float]] = {
    "haiku": (1.0, 5.0),
    "sonnet": (3.0, 15.0),
    "opus": (5.0, 25.0),
}


# ---------------------------------------------------------------------------
# Shared fuzzy matching (one definition for extraction recall/precision/attrib)
# ---------------------------------------------------------------------------

def text_overlap(a: str, b: str) -> float:
    """Word-overlap ratio in [0, 1]: |A∩B| / max(|A|, |B|)."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / max(len(words_a), len(words_b))


def best_overlap(text: str, candidates: list[str]) -> float:
    """Highest overlap between `text` and any candidate (0.0 if none)."""
    return max((text_overlap(text, c) for c in candidates), default=0.0)


def slugify_screen(name: str) -> str:
    """Normalize a target_screen name to a comparable slug."""
    slug = name.lower().replace(" ", "-")
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    return re.sub(r"-+", "-", slug).strip("-")


# ---------------------------------------------------------------------------
# Semantic claim matcher (plan §4) — one LLM-judge primitive, used twice:
#   * extraction scoring (open #3): the 0.6 word-overlap matcher under-reports
#     ~92% semantic recall as ~12% because an LLM paraphrase rarely shares enough
#     words verbatim. The judge matches by MEANING.
#   * E2E verdict→GT id alignment (open #4): real extraction IDs don't line up
#     with GT IDs, so verdicts must be remapped to GT before the confusion matrix.
# The word-overlap matcher is kept as a cheap pre-filter and an offline fallback.
# This lives in metrics.py (the sole GT reader), so it stays L1-clean.
# ---------------------------------------------------------------------------

_MATCH_PROMPT = """You are matching product-documentation claims by MEANING, to measure extraction recall.

The extraction often SPLITS one documented fact into several atomic claims: a
toolbar's item list becomes one claim per item; "the operators are A, B, C" becomes
one claim per operator; "X and Y are hidden in view mode" becomes two claims. So a
candidate counts as a MATCH when it expresses the SAME fact as the ground-truth (GT)
claim OR a clear CONSTITUENT PART of it — the same UI control, value, navigation
step, or behavior. Match generously on meaning, not on shared words. Return null
only when NO candidate is about the same thing at all.

For each GT claim below, pick the id of the single best-matching candidate (or null).
Return ONLY a JSON object mapping each GT id to a candidate id (a string) or null.
No explanation, no markdown.

{blocks}
"""

# Top word-overlap candidate at/above this ratio is accepted without the LLM judge
# (a strong lexical match the judge sometimes drops in a large batch). The judge
# still handles the harder paraphrase / compound-claim cases below the floor.
_OVERLAP_FLOOR = 0.45

# In-process memo so a single run computes each (dataset, content) match once.
_MATCH_MEM: dict[str, dict[str, str | None]] = {}


def _match_signature(extracted: list[dict], gt_claims: list[dict]) -> str:
    h = hashlib.sha256()
    for g in sorted(gt_claims, key=lambda c: c.get("id", "")):
        h.update(f"{g.get('id')}|{g.get('text', '')}".encode("utf-8"))
    h.update(b"##")
    for e in sorted(extracted, key=lambda c: c.get("id", "")):
        h.update(f"{e.get('id')}|{e.get('text', '')}".encode("utf-8"))
    return h.hexdigest()[:16]


def _match_cache_path(dataset_id: str | None) -> Path:
    MATCH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return MATCH_CACHE_DIR / f"{dataset_id or 'adhoc'}.json"


def _load_match_cache(dataset_id: str | None, sig: str) -> dict[str, str | None] | None:
    p = _match_cache_path(dataset_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8")).get(sig)
    except (json.JSONDecodeError, OSError):
        return None


def _save_match_cache(dataset_id: str | None, sig: str, mapping: dict[str, str | None]) -> None:
    p = _match_cache_path(dataset_id)
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (json.JSONDecodeError, OSError):
        data = {}
    data[sig] = mapping
    try:
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def _word_overlap_match(
    extracted: list[dict], gt_claims: list[dict], threshold: float = 0.6
) -> dict[str, str | None]:
    """Offline fallback / pre-filter: best-overlap extracted id per GT claim."""
    out: dict[str, str | None] = {}
    for g in gt_claims:
        best_id, best_ov = None, 0.0
        for e in extracted:
            ov = text_overlap(e.get("text", ""), g.get("text", ""))
            if ov > best_ov:
                best_ov, best_id = ov, e.get("id")
        out[g.get("id", "")] = best_id if best_ov >= threshold else None
    return out


def _candidates(extracted: list[dict], gt_text: str, k: int = 12) -> list[dict]:
    """Top-k extracted claims by word overlap — the LLM judge's shortlist.

    We pass the k most lexically-similar candidates (no hard floor): even a
    paraphrase shares a few content words, so the true match is almost always in
    the top-k, while the judge does the meaning-level decision.
    """
    scored = sorted(
        ((text_overlap(e.get("text", ""), gt_text), e) for e in extracted),
        key=lambda x: x[0], reverse=True,
    )
    return [e for _, e in scored[:k]]


def _llm_match_call(
    extracted: list[dict], gt_claims: list[dict], *, model: str, k: int
) -> dict[str, str | None] | None:
    """One LLM-judge call over a chunk of GT claims: gt_id -> ext_id|None.

    None on CLI failure (so the caller can fall back). Each GT claim is presented
    with its top-k word-overlap candidates; the judge picks the best by meaning.
    """
    from .claude_runner import run_claude  # lazy: keep metrics importable w/o claude

    valid_ext = {e.get("id") for e in extracted}
    blocks = []
    for g in gt_claims:
        lines = [f"GT {g.get('id')}: {g.get('text', '')}", "  candidates:"]
        cands = _candidates(extracted, g.get("text", ""), k=k)
        if cands:
            lines += [f"    - {c.get('id')}: {c.get('text', '')}" for c in cands]
        else:
            lines.append("    - (none)")
        blocks.append("\n".join(lines))

    prompt = _MATCH_PROMPT.replace("{blocks}", "\n\n".join(blocks))
    resp = run_claude(prompt, model=model, json_output=True)
    if not resp.get("success"):
        return None
    parsed = resp.get("parsed")
    if isinstance(parsed, dict) and isinstance(parsed.get("result"), dict):
        parsed = parsed["result"]
    if not isinstance(parsed, dict):
        return None

    out: dict[str, str | None] = {}
    for g in gt_claims:
        v = parsed.get(g.get("id", ""))
        out[g.get("id", "")] = v if (isinstance(v, str) and v in valid_ext) else None
    return out


def _llm_match(
    extracted: list[dict], gt_claims: list[dict], *, model: str, k: int = 12, chunk: int = 5
) -> dict[str, str | None] | None:
    """Judge GT claims in small chunks (reliability: a large batch makes the model
    drop clear matches — empirically chunks of ~5 are reliable, 8+ degrade).
    Returns the merged map, or None if EVERY chunk fails.
    """
    out: dict[str, str | None] = {}
    any_ok = False
    for i in range(0, len(gt_claims), chunk):
        part = gt_claims[i:i + chunk]
        res = _llm_match_call(extracted, part, model=model, k=k)
        if res is None:
            for g in part:
                out[g.get("id", "")] = None
        else:
            any_ok = True
            out.update(res)
    return out if any_ok else None


def semantic_match(
    extracted: list[dict],
    gt_claims: list[dict],
    *,
    dataset_id: str | None = None,
    use_llm: bool = True,
    model: str | None = None,
) -> dict[str, str | None]:
    """Match each GT claim to its best-expressing extracted claim by meaning.

    Returns gt_id -> ext_id (or None). Two-stage, L1-clean: (1) accept the top
    word-overlap candidate when it clears `_OVERLAP_FLOOR` (a strong lexical match
    the judge sometimes drops in a big batch); (2) send the rest to the chunked
    LLM judge, which matches generously by meaning (incl. compound GT claims the
    extractor split into atoms). Falls back to pure word-overlap when the CLI is
    unavailable. Cached per (dataset_id, content signature), in-process and on disk.
    """
    sig = _match_signature(extracted, gt_claims)
    if sig in _MATCH_MEM:
        return _MATCH_MEM[sig]
    cached = _load_match_cache(dataset_id, sig)
    if cached is not None:
        _MATCH_MEM[sig] = cached
        return cached

    mapping: dict[str, str | None] = {}
    remaining: list[dict] = []
    if extracted and gt_claims:
        for g in gt_claims:
            cands = _candidates(extracted, g.get("text", ""))
            if cands and text_overlap(cands[0].get("text", ""), g.get("text", "")) >= _OVERLAP_FLOOR:
                mapping[g.get("id", "")] = cands[0].get("id")
            else:
                remaining.append(g)
    else:
        remaining = list(gt_claims)

    judged: dict[str, str | None] | None = None
    if use_llm and remaining and extracted:
        judged = _llm_match(extracted, remaining, model=model or config.MODEL_MATCH)
    if judged is None:
        # CLI unavailable (or nothing to judge): pure word-overlap on the remainder.
        judged = _word_overlap_match(extracted, remaining)
    mapping.update(judged)

    _MATCH_MEM[sig] = mapping
    _save_match_cache(dataset_id, sig, mapping)
    return mapping


def alignment_for(
    dataset_id: str, extracted: list[dict], manifest_path: Path | None = None
) -> dict[str, str]:
    """ext_id -> gt_id semantic alignment for E2E verdict scoring (open item #4).

    The inverse of `semantic_match` (gt->ext): a verdict on an extracted claim is
    scored against the GT claim it expresses. Unmatched extracted claims are
    omitted (they are extraction false positives, not verification errors).
    """
    gt = _load_ground_truth(dataset_id, manifest_path)
    gt2ext = semantic_match(extracted, gt.claims, dataset_id=dataset_id)
    return {ext_id: gid for gid, ext_id in gt2ext.items() if ext_id}


# ---------------------------------------------------------------------------
# Ground-truth reader (L1: the sole reader of is_correct/expected_findings/mutation)
# ---------------------------------------------------------------------------

@dataclass
class GroundTruth:
    dataset_id: str
    is_correct: dict[str, bool]
    claims: list[dict]
    expected_findings: list[str]
    is_mutated: bool
    mutation: dict | None


def _load_ground_truth(dataset_id: str, manifest_path: Path | None = None) -> GroundTruth:
    """Read the ground-truth labels for one dataset entry from the manifest.

    PRIVATE BY CONTRACT (L1): prediction modules must never call this. Only the
    scoring functions below — and, through them, the evaluators — may use it.
    """
    path = manifest_path or config.MANIFEST_PATH
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if entry.get("id") == dataset_id:
                claims = entry.get("claims", [])
                return GroundTruth(
                    dataset_id=dataset_id,
                    is_correct={c["id"]: c["is_correct"] for c in claims},
                    claims=claims,
                    expected_findings=list(entry.get("expected_findings", [])),
                    is_mutated=entry.get("is_mutated", False),
                    mutation=entry.get("mutation"),
                )
    raise ValueError(f"Dataset '{dataset_id}' not found in manifest {path}")


def oracle_claims(dataset_id: str, manifest_path: Path | None = None) -> list[dict]:
    """DEBUG ONLY: ground-truth claims shaped as extractor inputs, labels stripped.

    Lets `--oracle-claims` seed plan/drive/verify from canonical claims to test the
    downstream chain without extraction noise. The `is_correct` labels never leave
    `metrics.py` (L1) — only claim text/type/target_screen/line_number are returned.
    Never used for headline extraction metrics.
    """
    gt = _load_ground_truth(dataset_id, manifest_path)
    return [
        {
            "id": c["id"],
            "text": c["text"],
            "type": c["type"],
            "target_screen": c["target_screen"],
            "line_number": c.get("line_number", 0),
        }
        for c in gt.claims
    ]


# ---------------------------------------------------------------------------
# Verification scoring — canonical confusion matrix (detection framing)
# ---------------------------------------------------------------------------

@dataclass
class VerificationScore:
    """Confusion matrix where positive == contradiction present (is_correct False)."""

    dataset_id: str
    tp: int = 0          # is_correct False & verdict false  -> contradiction caught
    fp: int = 0          # is_correct True  & verdict false  -> false alarm
    fn: int = 0          # is_correct False & verdict true   -> MISSED contradiction
    tn: int = 0          # is_correct True  & verdict true
    uncertain: int = 0   # abstention (never folded into FP/FN)
    no_verdict: int = 0  # claim had no verdict at all (coverage gap)
    contradiction_abstentions: int = 0  # uncertain on is_correct False (a soft miss)
    fp_claims: list[str] = field(default_factory=list)
    fn_claims: list[str] = field(default_factory=list)
    uncertain_claims: list[str] = field(default_factory=list)
    is_mutated: bool = False
    expected_findings: list[str] = field(default_factory=list)
    detected: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.tp + self.fp + self.fn + self.tn + self.uncertain + self.no_verdict

    @property
    def decided(self) -> int:
        return self.tp + self.fp + self.fn + self.tn

    @property
    def coverage(self) -> float:
        return self.decided / self.total if self.total else 0.0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        """Detection sensitivity: caught contradictions / all contradictions decided."""
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def accuracy(self) -> float:
        return (self.tp + self.tn) / self.decided if self.decided else 0.0

    @property
    def mutation_detected(self) -> bool:
        if not self.expected_findings:
            return False
        return set(self.detected) == set(self.expected_findings)

    def as_dict(self) -> dict[str, Any]:
        d = {
            "dataset_id": self.dataset_id,
            "tp": self.tp, "fp": self.fp, "fn": self.fn, "tn": self.tn,
            "uncertain": self.uncertain, "no_verdict": self.no_verdict,
            "contradiction_abstentions": self.contradiction_abstentions,
            "total": self.total, "decided": self.decided,
            "coverage": round(self.coverage, 3),
            "precision": round(self.precision, 3),
            "recall": round(self.recall, 3),
            "accuracy": round(self.accuracy, 3),
            "fp_claims": self.fp_claims,
            "fn_claims": self.fn_claims,
        }
        if self.is_mutated or self.expected_findings:
            d["expected_findings"] = self.expected_findings
            d["detected"] = self.detected
            d["mutation_detected"] = self.mutation_detected
        return d


def score_verdicts(
    verdict_results: dict[str, str],
    dataset_id: str,
    manifest_path: Path | None = None,
    *,
    alignment: dict[str, str] | None = None,
) -> VerificationScore:
    """Score verdicts against ground truth.

    Args:
        verdict_results: claim_id -> "true" | "false" | "uncertain".
        alignment: optional ext_id -> gt_id map (open item #4). For a real E2E run
            the verdict keys are *extracted* claim ids, which don't line up with GT
            ids; the alignment remaps them so the confusion matrix is trustworthy.
            Unmatched extracted verdicts (no GT) are dropped here — they are
            extraction false positives, not verification false alarms; unmatched GT
            claims simply get no verdict (a coverage gap, not a missed
            contradiction). The oracle path passes no alignment (IDs already match).
    """
    gt = _load_ground_truth(dataset_id, manifest_path)
    if alignment is not None:
        remapped: dict[str, str] = {}
        for ext_id, result in verdict_results.items():
            gid = alignment.get(ext_id)
            if gid is not None:
                remapped[gid] = result  # collisions (rare) resolve last-wins
        verdict_results = remapped
    score = VerificationScore(
        dataset_id=dataset_id,
        is_mutated=gt.is_mutated,
        expected_findings=list(gt.expected_findings),
    )

    for claim_id, is_correct in gt.is_correct.items():
        result = verdict_results.get(claim_id)
        if result is None:
            score.no_verdict += 1
            continue
        if result == "uncertain":
            score.uncertain += 1
            score.uncertain_claims.append(claim_id)
            if not is_correct:
                score.contradiction_abstentions += 1
            continue

        verdict_false = result == "false"
        if not is_correct:                      # contradiction present (positive)
            if verdict_false:
                score.tp += 1                   # caught
            else:
                score.fn += 1                   # missed contradiction — the costly one
                score.fn_claims.append(claim_id)
        else:                                   # no contradiction (negative)
            if verdict_false:
                score.fp += 1                   # false alarm
                score.fp_claims.append(claim_id)
            else:
                score.tn += 1

    score.detected = [
        ef for ef in gt.expected_findings if verdict_results.get(ef) == "false"
    ]
    return score


# ---------------------------------------------------------------------------
# Extraction scoring — recall / precision / type / attribution (one matcher)
# ---------------------------------------------------------------------------

@dataclass
class ExtractionScore:
    dataset_id: str
    gt_count: int
    extracted_count: int
    matched: int
    type_matches: int
    attribution_matches: int
    missed: list[str] = field(default_factory=list)
    threshold: float = 0.6

    @property
    def recall(self) -> float:
        return self.matched / self.gt_count if self.gt_count else 0.0

    @property
    def precision(self) -> float:
        return self.matched / self.extracted_count if self.extracted_count else 0.0

    @property
    def type_accuracy(self) -> float:
        return self.type_matches / self.matched if self.matched else 0.0

    @property
    def attribution_accuracy(self) -> float:
        return self.attribution_matches / self.matched if self.matched else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "gt_claims": self.gt_count,
            "extracted_claims": self.extracted_count,
            "matched": self.matched,
            "recall": round(self.recall, 3),
            "precision": round(self.precision, 3),
            "type_accuracy": round(self.type_accuracy, 3),
            "attribution_accuracy": round(self.attribution_accuracy, 3),
        }


def score_extraction(
    extracted: list[dict],
    dataset_id: str,
    manifest_path: Path | None = None,
    threshold: float = 0.6,
    *,
    semantic: bool = True,
) -> ExtractionScore:
    """Score extracted claims against ground truth (open item #3 fix).

    Each GT claim is matched to its single best-expressing extracted claim by the
    semantic matcher (meaning, not word overlap); type and attribution accuracy
    are measured only over matches. Pass `semantic=False` to fall back to the pure
    0.6 word-overlap matcher (offline / no-CLI).
    """
    gt = _load_ground_truth(dataset_id, manifest_path)
    ext_by_id = {e.get("id"): e for e in extracted}
    if semantic:
        gt2ext = semantic_match(extracted, gt.claims, dataset_id=dataset_id)
    else:
        gt2ext = _word_overlap_match(extracted, gt.claims, threshold)

    matched = 0
    type_matches = 0
    attribution_matches = 0
    missed: list[str] = []

    for gtc in gt.claims:
        ext_id = gt2ext.get(gtc["id"])
        best = ext_by_id.get(ext_id) if ext_id else None
        if best is not None:
            matched += 1
            if best.get("type") == gtc.get("type"):
                type_matches += 1
            if slugify_screen(best.get("target_screen", "")) == slugify_screen(
                gtc.get("target_screen", "")
            ):
                attribution_matches += 1
        else:
            missed.append(gtc["text"])

    return ExtractionScore(
        dataset_id=dataset_id,
        gt_count=len(gt.claims),
        extracted_count=len(extracted),
        matched=matched,
        type_matches=type_matches,
        attribution_matches=attribution_matches,
        missed=missed,
        threshold=threshold,
    )


# ---------------------------------------------------------------------------
# Cost cross-check against the rate card
# ---------------------------------------------------------------------------

def estimate_cost(model: str, usage: dict | None) -> float | None:
    """Rough USD estimate from token usage and the rate card (cross-check only).

    `model` may be an alias ("haiku") or a full id ("claude-haiku-4-5-...").
    Returns None if the model/usage can't be priced.
    """
    if not usage:
        return None
    rate = None
    for alias, r in RATE_CARD.items():
        if alias in model:
            rate = r
            break
    if rate is None:
        return None
    in_tok = (
        (usage.get("input_tokens") or 0)
        + (usage.get("cache_read_input_tokens") or 0)
        + (usage.get("cache_creation_input_tokens") or 0)
    )
    out_tok = usage.get("output_tokens") or 0
    return in_tok / 1_000_000 * rate[0] + out_tok / 1_000_000 * rate[1]


# ---------------------------------------------------------------------------
# Loaders for prediction outputs (not ground truth — safe for evaluators)
# ---------------------------------------------------------------------------

def load_verdict_results(dataset_id: str) -> dict[str, str]:
    """claim_id -> result string, read from results/verdicts/{dataset_id}.json."""
    path = config.VERDICTS_DIR / f"{dataset_id}.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {v["claim_id"]: v["result"] for v in data}


def load_extracted_claims(dataset_id: str) -> list[dict]:
    """Extracted claim dicts from results/claims/{dataset_id}.json."""
    path = config.CLAIMS_DIR / f"{dataset_id}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Human-readable formatting
# ---------------------------------------------------------------------------

def format_verification(score: VerificationScore) -> str:
    lines = [
        "=" * 64,
        f"  Verification: {score.dataset_id}   (mutated={score.is_mutated})",
        "  Detection framing: positive = contradiction present (is_correct=False)",
        "=" * 64,
        f"  Total claims        : {score.total}",
        f"  Decided             : {score.decided}   (coverage {score.coverage:.1%})",
        f"  Uncertain (abstain) : {score.uncertain}",
    ]
    if score.no_verdict:
        lines.append(f"  No verdict          : {score.no_verdict}")
    lines += [
        "  ---- confusion matrix ----",
        f"  TP  caught          : {score.tp}",
        f"  FP  false alarm     : {score.fp}   {score.fp_claims or ''}",
        f"  FN  MISSED          : {score.fn}   {score.fn_claims or ''}",
        f"  TN                  : {score.tn}",
        "  ---- derived ----",
        f"  Precision           : {score.precision:.1%}",
        f"  Recall (sensitivity): {score.recall:.1%}",
        f"  Accuracy (decided)  : {score.accuracy:.1%}",
        f"  Contradiction abstentions: {score.contradiction_abstentions}",
    ]
    if score.is_mutated or score.expected_findings:
        lines += [
            "  ---- mutation ----",
            f"  Expected findings   : {score.expected_findings}",
            f"  Detected (false)    : {score.detected}",
            f"  Mutation detected   : {score.mutation_detected}",
        ]
    lines.append("=" * 64)
    return "\n".join(lines)


def format_extraction(score: ExtractionScore) -> str:
    return "\n".join([
        "=" * 64,
        f"  Extraction: {score.dataset_id}",
        "=" * 64,
        f"  Ground truth claims : {score.gt_count}",
        f"  Extracted claims    : {score.extracted_count}",
        f"  Matched             : {score.matched}",
        f"  Recall              : {score.recall:.1%}",
        f"  Precision           : {score.precision:.1%}",
        f"  Type accuracy       : {score.type_accuracy:.1%}",
        f"  Attribution accuracy: {score.attribution_accuracy:.1%}",
        "=" * 64,
    ])

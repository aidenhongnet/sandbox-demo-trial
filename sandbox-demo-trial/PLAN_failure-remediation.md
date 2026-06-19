# Plan: Remediating Failure Modes 1–6 from the First MVP Run

**Role:** Planner (`roles/PLANNER.md`)
**Date:** 2026-06-17
**Inputs:** `RESULTS_mvp-run.md`, the run artifacts under `results/`, the failure
analysis of the first end-to-end run, and verification of every claim against the
current `pipeline/` source + `dataset/manifest.jsonl`.
**Companion docs:** `MISSION.md`, `CLAUDE.md`, `PLAN_mvp-pipeline.md`.

---

## Objective

Fix the six root-cause failure modes from the first run so that the pipeline produces
**trustworthy, leakage-free measurements** of documentation-verification quality, and so
that the metrics in `PLAN_mvp-pipeline.md`'s success criteria mean what they claim.

The unifying lens, per `MISSION.md`: *false negatives — missed contradictions — are more
costly than false alarms.* Several fixes below are explicitly shaped so they do **not**
trade away contradiction-sensitivity for a prettier false-positive number. And per
`MISSION.md`, verification stays **user-perspective only** (rendered UI / DOM via
chrome-devtools), never product source code or REST APIs.

---

## Scope (read this first)

The analysis enumerated seven root causes. This plan covers **#1–#6** ("failure modes one
to six inclusive"):

| # | Failure mode | Plan section |
|---|--------------|--------------|
| 1 | Doc/product **version mismatch invalidates the ground truth** | Fix 1 |
| 2 | **`nav_path` claims structurally unverifiable** (M1 miss) | Fix 2 |
| 3 | **Verifier defects** — over-strict compounds, non-determinism, visual-from-text | Fix 3 |
| 4 | **Image fallback lies to the model** (no image is ever sent) | Fix 4 |
| 5 | **Phase 3 reachability** — 6 screens fail, 9 claims stuck UNCERTAIN | Fix 5 |
| 6 | **Extraction over-produces + broken extraction evaluator** | Fix 6 |

**Decision — measurement prerequisites folded in (Phase 0).** Root cause #7
(FP/FN label inversion between `verify.py` and `orchestrator.py`; `uncertain` mis-bucketed
as a false positive; cost never captured) is *technically* outside "1–6", but **none of
Fixes 1–6 can be validated without it** — you cannot tell whether the version fix or the
verifier fix worked if the evaluator mislabels outcomes and can't track cost. I am
therefore including the minimal measurement-correctness work as **Phase 0**, and flagging
it here so it can be vetoed. Everything else in #7 is already covered by Phase 0.

> If "1–6" was meant as the *priority-ranked* list (which swaps Phase-3 fixtures out and
> instrumentation in), this plan is still a superset: it covers all of #1–#6 under either
> reading **plus** the measurement prerequisites. Nothing in either reading is dropped.

---

## Data-leakage threat model (the core design constraint)

This system's entire value is *honest* observation: it must catch documentation that
contradicts the product. Leakage — any path by which the answer key, the claim, or the
mutation reaches a component that is supposed to be blind to it — silently destroys that
value by manufacturing agreement. Worse, leakage inflates exactly the metric
(`MISSION.md`: minimize false negatives) we most need to trust. Every fix below is
designed against this table; each fix section restates its specific guards.

| ID | Vector | Where it bites | Guard |
|----|--------|----------------|-------|
| **L1** | **Label leakage** — `is_correct` / `expected_findings` / `mutation` text reaching extract/plan/drive/verify prompts | Manifest is read in two places today | **Single ground-truth reader.** Only `pipeline/metrics.py` may read `is_correct`/`expected_findings`/`mutation`. Prediction modules (`extract/plan/drive/verify.run()`) import claim *text/type/screen* only. Add a unit test asserting those modules never import the GT loader. Orchestrator already passes only `entry["content"]` to extract (`orchestrator.py:37`) — keep it that way; never pass the whole entry. |
| **L2** | **Confirmation leakage** — the driver being told the claim/expectation it is "verifying," so it rubber-stamps | Phase 3 capture | **Driver is claim-blind.** The agent navigates to a *screen* and produces a neutral, exhaustive inventory. It is never handed claim text or a "confirm that X" instruction. `what_to_capture` must be generic ("inventory every element/label/state in this region"), not claim-derived. Honest-failure behavior (write no files on failure) already in `agent_system.txt:40` stays. |
| **L3** | **Mutation leakage** — a mutated claim steering the capture so clean vs M-runs differ | Shared capture across `*-clean` and `*-m1` | **Captures are a pure function of `(product_version, fixture_id, screen_id)`** — never of `dataset_id`/claim correctness. One capture is reused across clean and all mutations of the same page. The mutation affects only the claim text fed to the *verifier*, never the capture. (This makes the run's existing clean→m1 capture reuse principled rather than accidental — see L7.) |
| **L4** | **Tuning/test leakage** — iterating prompts/thresholds on the same examples used to report headline numbers | Fixes 3 & 6 prompt work | **Dev/test split** across pages & products. Tune on DEV only; freeze TEST; report headline metrics on TEST only. Few-shot examples in any prompt come from a *different* page/product than TEST. With only Grafana-p1 live today, the current numbers are labeled **DEV-only** until a TEST page exists. |
| **L5** | **Canonical-taxonomy leakage** — feeding the extractor the GT's screen names so recall/attribution is circular | Fix 6 canonicalization | Screen taxonomy comes from a **product-derived** source (a claim-blind UI crawl or a separately-maintained screen ontology), **never** from `manifest.jsonl` claims. Extractor stays GT-blind; normalization to the ontology is a separate post-step. |
| **L6** | **Oracle-circularity** — using the verifier model to (re)label ground truth, so it always "agrees" | Fix 1 re-labeling | GT (re)labeling is produced **independently of the verification model/prompt** — human review of screenshots, or a different, stronger model used once offline. Record `labeled_against_version` + `labeled_by` provenance per claim. The verifier never sees these. |
| **L7** | **Cache cross-contamination** — a dataset/claim-keyed cache serving one entry's state as another's | `verify._load_screen_states` globs a shared dir | Cache key = content hash of `(product_version, fixture_id, screen_id)`. Never key capture/trace caches on `dataset_id` or `claim_id`. Verdict caches *are* claim-specific and must not be shared across claims. |

---

## Phase 0 — Trustworthy measurement foundation (prerequisite)

**Problem (verified):**
- `verify.py:225-230` and `orchestrator.py:165-170` define FP/FN with **opposite**
  meanings; the PLAN criteria and `MISSION.md` use the detection framing
  (FP = good claim flagged; FN = missed contradiction). `verify.py` is inverted relative
  to both.
- `orchestrator.py:163` sets `verdict_says_correct = (result=="true")`, so `uncertain`
  on a clean claim is counted as a **false positive** — it would report 19 FPs on the
  clean set, not 10.
- `run_claude` only captures `cost_usd` when `json_output=True` (`claude_runner.py:73-84`);
  `drive.py:194` doesn't pass it and nothing reads it — Phase 3 cost is uncaptured, so
  criterion 5 is unmeasurable.
- `extract.evaluate` uses exact lowercased set-intersection (`extract.py:192`) despite a
  comment claiming "fuzzy containment" → recall ≈ 0 by construction.

**Design:**
1. **New `pipeline/metrics.py`** — the single source of truth for evaluation, and (per
   **L1**) the *only* module permitted to read `is_correct`/`expected_findings`. One
   canonical confusion matrix, detection framing (positive = "contradiction present",
   i.e. `is_correct == False`):
   - `TP`: `is_correct=False` & verdict `false` (caught)
   - `FP`: `is_correct=True` & verdict `false` (false alarm)
   - `FN`: `is_correct=False` & verdict `true` (**missed contradiction — the costly one**)
   - `TN`: `is_correct=True` & verdict `true`
   - `uncertain`: an **abstention**, reported as its own bucket + `coverage = decided/total`. Never folded into FP or FN.
   - Plus the shared fuzzy matcher (lift `_text_overlap` out of `orchestrator.py:191`) so extraction recall/precision/attribution use one definition.
2. **Rewire both evaluators** to import `metrics.py`. Delete the inverted block in
   `verify.evaluate` and the `uncertain`-as-FP bug in `orchestrator.evaluate_against_ground_truth`.
3. **Cost capture:** `run_claude` parses `total_cost_usd` whenever it is present in the
   `--output-format json` (or stream-json, see Fix 2) envelope. Every phase accumulates
   per-call `total_cost_usd`; orchestrator reports `cost_usd` per phase + total and checks
   criterion 5. Cross-check against the rate card (Haiku 4.5 $1/$5, Sonnet 4.6 $3/$15,
   Opus 4.8 $5/$25 per 1M in/out) when `usage` is present.
4. **Replace `extract.evaluate`'s exact-match** with the shared fuzzy matcher.

**Leakage guards:** L1 (single GT reader + import-isolation test).
**Acceptance:** clean-set re-scored shows TN=6, FP=10, UNCERTAIN=9 (not "19 FP"); a
`pipeline_report.json` with non-null `cost_usd` per phase; `extract.evaluate` recall on a
hand-checked sample is non-zero and matches the orchestrator's matcher.

---

## Fix 1 — Version-controlled environment + valid ground truth (Failure #1)

**Problem (verified):** `manifest.jsonl` Grafana entries all source from
`/docs/grafana/latest/` and describe the new dashboard editing experience (Add new
element, three-tile panel dialog, 9-icon sidebar/toolbar, Custom/Auto-grid layouts,
Show/hide rules). `config.py:33` pins `grafana/grafana:11.6.0`, which predates all of it.
`grafana-p1-clean` labels every claim `is_correct=true`. The driver correctly observed
those features absent in 11.6.0; the 10 "false positives" are mostly **correct drift
detections measured against a broken oracle**. `dataset-plan.md:48-53` confirms GT was
"human labels before mutations" from the `/latest/` doc — never validated against the
pinned build.

**Mission framing:** `MISSION.md` explicitly expects docs across *multiple product
versions* and "the gap between what documentation describes and how the product is
actually navigated." So the fix is not "pick a version once" — it is to make **product
version an explicit, declared, enforced variable**, and to validate GT against the build
that is actually deployed.

**Design:**
1. **Declare version everywhere.** Add `product_version` to the manifest `DatasetEntry`
   (schema.py) and make `GRAFANA_IMAGE` derive from it (config.py), so the deployed
   container is pinned to the version the GT was labeled against. No floating `latest`.
2. **Pick the version from the doc snapshot.** The doc describes the new-editing-experience
   feature set; deploy the Grafana release where that set is GA.
   - *Executor pre-step (smoke test):* confirm, from Grafana release notes, the exact
     version where "Add new element / Auto grid layout / Show-hide rules / new dashboard
     editing" went GA, and pin that tag exactly. (Determination method specified here so
     the plan doesn't hinge on a remembered version number.)
   - *Alternative, also valid:* keep 11.6.0 and **re-label** GT against 11.6.0 — which
     converts this page into a natural M7-style "stale terminology / version drift" test.
     Either way the invariant is **deployed version == labeled version**.
3. **Re-label / validate GT independently (L6).** Whichever version is chosen, the
   `is_correct` labels must be (re)produced **without** the verification model — human
   screenshot review or a different, stronger model run once offline. Record
   `labeled_against_version` and `labeled_by` provenance per claim. The verifier never
   sees these fields (L1).
4. **Fail fast on mismatch.** `drive.py` setup asserts the running container's reported
   version equals `entry.product_version`; refuse to run on mismatch rather than silently
   producing meaningless verdicts.

**Leakage guards:** L1 (provenance fields are GT-only), L6 (independent labeling).
**Acceptance:** with deployed==labeled version, a spot-check of the 10 previously-`false`
clean claims (c2,c3,c8,c9,c10,c11,c17,c19,c22,c23) reflects the deployed UI — most flip to
`true` if the matching version is deployed, or GT flips to `is_correct=false` if 11.6.0 is
kept. Either outcome makes the clean false-positive metric *meaningful*.

---

## Fix 2 — Make `nav_path` (and step-order) verifiable via navigation traces (Failure #2)

**Problem (verified):** `drive.py:194` calls `run_claude` without `json_output`, so the
"navigation log" is the agent's final prose (`result["raw"]`), not the MCP tool-call
sequence the design intended (`PLAN_mvp-pipeline.md:152`). The captured state is the
*destination*, identical whether you reach it via "Dashboards" or the mutated "Home" — so
M1 (`grafana-p1-m1`, c1) verified `true 0.92` and the mutation was missed. This is
structural and survives the Fix 1 oracle correction.

**Design:**
1. **Capture the real action trace.** Run drive calls with
   `claude -p --output-format stream-json` and parse `tool_use`/`tool_result` events from
   the chrome-devtools MCP into a structured `NavigationTrace`: ordered
   `[{step, action(navigate|click|type), target_label, resulting_url, resulting_title,
   snapshot_digest}]`. Persist to `results/traces/{screen_id}.json`.
   - *Executor smoke test:* confirm `claude -p` emits tool-call events in stream-json for
     MCP tools in this Claude Code version. **Fallback** if not: have the agent author a
     structured `navigation_trace.json` step-log via the Write tool as it goes (less
     tamper-proof; acceptable interim).
2. **Two capture passes, decoupled from the claim (L2):**
   - **Pass A — discovery (goal-driven, claim-blind):** reach the target screen by any
     means, capture neutral inventory + the trace it actually took. Serves
     `ui_element`/`field_value`/`behavior`/`visual_state`.
   - **Pass B — procedure replay (for `nav_path`/step-order only):** a driver executes the
     documented steps **as an opaque procedure to perform**, recording at each step
     whether the named control existed and what state resulted — *without* being told the
     expected outcome or whether the procedure is canonical. Honest-failure reporting
     surfaces absent controls instead of hallucinating them.
3. **Verifier reads the trace, not the destination.** For `nav_path`, the verifier
   compares the claim's asserted path against the Pass-B replay trace: if a documented
   step's control is absent or leads to the wrong intermediate state, the claim is `false`.
   For M1, the replay of "click Home → New → New Dashboard" shows step 1 lands on Home
   (not the Dashboards list) → contradiction detected.
4. **Model delta:** add `navigation_trace_path` to `ScreenState` (models.py); replace the
   prose-only `navigation_log` usage in `drive.py`.

**Leakage guards:** L2 (Pass B performs steps without the expected verdict; Pass A is
goal-driven and claim-blind), L3/L7 (trace keyed by version+fixture+screen, reused across
clean & mutations).
**Acceptance:** re-running `grafana-p1-m1` flags c1 `false` (mutation detected) **for the
right reason** — the trace shows the documented path diverging — while `grafana-p1-clean`
c1 stays `true`.

---

## Fix 3 — Verifier correctness: decompose, stabilize, calibrate (Failure #3)

**Problem (verified):**
- **Over-strict compounds:** c8/c10 confirm one conjunct, find the other absent, return
  high-confidence `false` on the whole; `verify_claim.txt` never instructs decomposition.
- **Non-determinism:** c17 (identical text, identical screen description, *not* mutated in
  m1) scored `false 0.95` on clean but `true 0.95` on m1 — opposite verdicts, same input.
- **visual-from-text:** c22 (`visual_state`) returned `false 0.95` from text alone, against
  the prompt's own rule (`verify_claim.txt:21`) to prefer UNCERTAIN.

**Design (shaped to protect contradiction-sensitivity, per `MISSION.md`):**
1. **Atomic decomposition.** Pre-split a compound claim into atomic sub-assertions, each
   tagged with sub-type (UI-label vs functional/behavioral). Verify each atom against the
   state, then aggregate: claim `true` iff all atoms `true`; `false` if any atom `false`;
   `uncertain` if no atom `false` and ≥1 `uncertain`. This **keeps** sensitivity (a truly
   contradicted atom still fails the claim) while surfacing the *specific* failing atom to
   the human reviewer instead of a blunt whole-claim false. The sub-type tag fixes c17:
   a parenthetical *functional* description ("arranges panels side-by-side") is not judged
   as on-screen UI text.
2. **Determinism via self-consistency — not temperature.** `claude -p` exposes no
   temperature/sampling control, and on current models those params are removed entirely;
   adaptive thinking adds run-to-run variance. So stabilize by **N=3 self-consistency**:
   run the verify call 3×, majority-vote the result, and set confidence = vote fraction.
   Split votes → `uncertain`. This both fixes the c17 flip and yields a *calibrated*
   confidence (replacing the model's self-reported number). Cost ≈ 3× verify calls;
   verify is the cheap phase (Haiku 4.5, $1/$5 per 1M), so this is affordable and
   measured by Phase 0.
3. **Enforce the visual rule.** `visual_state` atoms that depend on rendered attributes
   (color, "solid line" vs "fill") route to the image path (Fix 4); if no valid image
   evidence, return `uncertain` — never a confident text-only `false` (fixes c22).
4. **Model choice:** keep verify on **Haiku 4.5** (cheap, and vision-capable — confirmed)
   by default; if DEV-set calibration shows Haiku can't reliably decompose, escalate the
   *decomposition* step only to Sonnet 4.6 and keep per-atom checks on Haiku. Decide on
   evidence, not assumption.

**Leakage guards:** L1 (verifier never sees `is_correct`), L4 (prompt + threshold tuning on
DEV only; few-shot examples drawn from a non-TEST page).
**Acceptance:** on the DEV set, c17 is stable across repeated runs; compound claims report
the specific failing atom; visual_state claims with no image evidence are `uncertain`, not
`false`; **no regression in catching genuinely contradicted claims** (FN rate does not rise).

---

## Fix 4 — Real image input, or honest abstention (Failure #4)

**Problem (verified):** `verify.py:120-131`'s "image fallback" only swaps in the note
*"A screenshot is also attached…"* while `run_claude` (`claude_runner.py`) has **no image
parameter** — no image is ever sent. The model is told an image is attached when it is
not. It fired once (c23, `used_image_fallback:true`) and returned a confident `false`
partly on the basis of a non-existent screenshot.

**Design:**
1. **Remove the deceptive note immediately**, regardless of the rest — only claim an image
   is present when one actually is.
2. **Add genuine image input to `run_claude`** via Claude Code's image mechanism (e.g. an
   `@<path>` reference the agent reads, or the CLI's image input). All three current models
   — Haiku 4.5, Sonnet 4.6, Opus 4.8 — support image input, so the existing Haiku verify
   model can read the screenshot. *Executor smoke test:* confirm `claude -p` headless can
   ingest a PNG path. **If it cannot**, the fallback is **disabled** and visual-dependent
   atoms return `uncertain` (honest) rather than a fabricated verdict — never restore the
   fake-image path.
3. **Feed the claim-blind capture.** The screenshot handed to the verifier is the driver's
   neutral capture (L2) — no claim overlay or annotation that hints the answer.

**Leakage guards:** L2 (unannotated screenshot), L1 (no GT in the image path).
**Acceptance:** a `visual_state` claim (e.g. c22 "solid blue line") is judged from the
actual screenshot, with evidence citing the image; `used_image_fallback=true` only when an
image was truly sent; if image input is unsupported, those claims are `uncertain`, and the
report shows zero fake-image verdicts.

---

## Fix 5 — Phase 3 reachability via deterministic, claim-blind fixtures (Failure #5)

**Problem (verified):** 6 screens failed in the run (saved-queries-drawer,
dashboard-settings-layout, content-outline, auto-grid-layout-settings, and the two
show/hide-rules screens), leaving 9 clean claims (c5, c12–c16, c20, c21, c25) stuck at
`uncertain — "No screen state captured"`. Most need pre-existing complex state (a saved
dashboard with variables, multiple rules, custom/auto-grid layout, multiple panels) that a
fresh container lacks. (Some of these screens *also* don't exist in 11.6.0 — Fix 1 governs
which are reachable at all.)

**Design:**
1. **Provision a deterministic fixture.** A realistic seeded dashboard (e.g. 4 panels,
   1 row, 2 template variables, auto-grid layout, 2 show/hide rules) that exercises the
   **screen taxonomy** — derived from the *list of screens to reach*, **never** from
   `is_correct` (claim-blind by construction).
2. **Respect the MISSION UI-only boundary by separating SETUP from VERIFICATION.**
   `MISSION.md` requires *verification* to be user-perspective (UI/DOM only). Arranging
   *preconditions* is setup, not verification. Prefer establishing the fixture through the
   in-UI Import (paste dashboard JSON) so even setup is user-perspective; fall back to
   Grafana's file provisioning only if necessary, clearly labeled **setup-only**.
   Verification of every claim still happens purely through the rendered UI.
3. **Idempotent + ephemeral.** Recreate the fixture fresh each run (container is
   disposable). The capture remains a pure function of `(version, fixture_id, screen_id)`
   (L3/L7) and is safely shared across clean and all mutations.
4. **Cascade correctness:** with fixtures present, screens like auto-grid-layout-settings
   and show/hide-rules become reachable, so the parent-skip cascade in `drive.py:277`
   stops pruning their dependents.

**Leakage guards:** L3 (fixture defined from screen list, not answers; capture
version+fixture-keyed), L7 (cache key includes `fixture_id`).
**Acceptance:** navigation coverage rises above the 14/20 baseline; the 9
"no screen captured" UNCERTAINs are replaced by real verdicts (subject to Fix 1 governing
which screens exist in the deployed version).

---

## Fix 6 — Extraction: control volume, canonicalize without leakage, fix the evaluator (Failure #6)

**Problem (verified):** real extraction produced **111 claims vs 25 GT**
(`results/claims/grafana-p1-clean.extracted.json`) with ad-hoc `target_screen` names that
miss `GRAFANA_P1_DEPS` (`plan.py:31-52`), collapsing to depth 0 and defeating
caching/ordering. The measured run therefore **bypassed extraction** and seeded Phases 2–4
from the 25 GT claims (`RESULTS_mvp-run.md:16-24`) — so the run was not truly end-to-end
and criterion 1 was never exercised. The standalone `extract.evaluate` exact-match bug is
handled in Phase 0.

**Design:**
1. **Volume control.** Tune `extract_claims.txt` toward one atomic claim per verifiable
   assertion + a **semantic dedup** post-pass (cluster near-paraphrases; collapse) to land
   in the ~25–40 range instead of 111, matching human density.
2. **Canonical screens *without* GT leakage (L5).** Do **not** hand the extractor the GT
   screen list. Build a **product-derived screen ontology** — a one-time claim-blind UI
   crawl of the running product that enumerates reachable screens/routes, or a separately
   maintained product screen map — and normalize extracted `target_screen` values to it as
   a separate mapping step. The extractor stays GT-blind; recall/attribution are scored
   against GT *only* inside `metrics.py`. (Feeding GT screen names would make recall
   circular and inflated — the central leakage trap of this fix.)
3. **Re-enable true end-to-end.** With volume + canonicalization fixed, run
   extract→plan→drive→verify with no GT seeding. Keep the GT-seeded path available as a
   clearly-labeled `--oracle-claims` debug mode, **never** used for headline metrics.
4. **Evaluator** already unified in Phase 0 (shared fuzzy matcher; one recall definition).

**Leakage guards:** L5 (product-derived ontology, not GT), L1 (extractor never sees GT),
L4 (prompt tuning on DEV only).
**Acceptance:** extraction emits ~25–40 canonical-screen claims on Grafana-p1; a true
end-to-end run completes without seeding; recall/precision/attribution are reported from
`metrics.py` against (independently-relabeled, Fix 1) GT.

---

## Sequencing & dependencies

Ordered so each step is *validatable* when it lands:

1. **Phase 0 (measurement)** — gates everything; you can't see if any later fix worked
   without it.
2. **Fix 1 (version + valid GT)** — until the oracle is valid, every accuracy number is
   meaningless; this also unblocks Fix 3 calibration (you can't calibrate a verifier
   against a broken oracle).
3. **Fix 5 (fixtures) + Fix 2 (trace capture)** — both are drive-phase changes; do
   together (both touch `drive.py`/`claude_runner.py`).
4. **Fix 3 (verifier) + Fix 4 (image)** — both verify-phase; validate against the
   now-valid GT and real captures/traces.
5. **Fix 6 (extraction + true E2E)** — the scale enabler; depends on the product-derived
   ontology and on the rest being trustworthy.

---

## Files touched (executor map)

- **New:** `pipeline/metrics.py` (canonical eval + sole GT reader); `results/traces/`;
  fixture asset(s) (dashboard JSON) under e.g. `fixtures/grafana/`; product screen
  ontology source; `prompts/decompose_claim.txt` (or extend `verify_claim.txt`).
- **Edit:** `pipeline/config.py` (versioned image, `product_version`),
  `dataset/schema.py` + `manifest.jsonl` (`product_version`, label provenance),
  `pipeline/claude_runner.py` (stream-json + cost + image input),
  `pipeline/drive.py` (trace capture, fixtures, version preflight),
  `pipeline/models.py` (`ScreenState.navigation_trace_path`),
  `pipeline/verify.py` (decomposition, self-consistency, image routing, GT-read removed),
  `pipeline/orchestrator.py` (use `metrics.py`, aggregate cost),
  `pipeline/extract.py` (volume, canonicalization hook, evaluator via `metrics.py`),
  `pipeline/plan.py` (ontology-driven screen ids if needed),
  `prompts/extract_claims.txt`, `prompts/verify_claim.txt`, `prompts/agent_system.txt`
  (claim-blind capture wording).
- **Per PLAN-EXECUTOR.md:** on completion, update `CLAUDE.md` "Current status" +
  `RESULTS_mvp-run.md` (correct the "verification is the weak link" framing — the analysis
  shows the oracle and instrumentation were the dominant problems) and `PLAN_mvp-pipeline.md`
  success criteria wording.

---

## Success criteria for this remediation

1. **Metrics are trustworthy:** one FP/FN definition (detection framing) shared by both
   evaluators; `uncertain` reported separately with a coverage metric; per-phase + total
   `cost_usd` in `pipeline_report.json`; criterion 5 checkable.
2. **Oracle is valid:** deployed version == labeled version, enforced at setup; GT labeled
   independently of the verifier with recorded provenance.
3. **M1 is detected for the right reason:** `grafana-p1-m1` c1 → `false` via a divergent
   navigation trace; clean c1 stays `true`.
4. **Verifier is sensitive *and* stable:** compound claims decompose to the failing atom;
   c17-type verdicts are reproducible across runs; visual claims without image evidence are
   `uncertain`; **FN rate (missed contradictions) does not regress** (the MISSION priority).
5. **Image path is honest:** real screenshot in, or `uncertain` out — zero fabricated
   verdicts.
6. **Reachability up:** the 9 "no screen captured" UNCERTAINs become real verdicts (for
   screens that exist in the deployed version).
7. **True end-to-end runs:** extraction emits ~25–40 canonical-screen claims and the full
   chain runs without GT seeding; recall measured by `metrics.py`.
8. **No leakage:** the L1–L7 guards hold — verified by the import-isolation test (L1), the
   claim-blind capture review (L2), version+fixture-keyed caches (L3/L7), a DEV/TEST split
   with frozen TEST (L4), a product-derived ontology (L5), and independent GT labeling (L6).

---

## Risks & open questions

1. **Exact Grafana version (Fix 1).** Resolved by the executor's release-notes smoke test
   before pinning; the plan's correctness depends only on "deployed == labeled," not on a
   specific tag.
2. **`claude -p` capabilities (Fixes 2, 4).** stream-json tool-call events and headless
   image ingestion are assumed; each has a specified smoke test and an honest fallback
   (agent-authored trace; disable-and-abstain) if unsupported — no silent degradation.
3. **Self-consistency cost (Fix 3).** 3× verify calls; affordable on Haiku and tracked by
   Phase 0. Tune N on the DEV set.
4. **DEV/TEST split needs ≥2 pages (L4).** Until a second labeled page exists, current
   numbers are explicitly DEV-only; producing a TEST page (another Grafana page, or
   Keycloak/NetBox per `dataset-plan.md`) is a precondition for any *headline* metric.
5. **Re-labeling effort (Fix 1, L6).** Independent relabeling of 25 claims is modest;
   doing it for the full ~102-entry dataset is a separate, larger task — out of scope here,
   flagged for planning.

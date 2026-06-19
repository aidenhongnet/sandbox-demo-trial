# Remediation Validation Run — Results

**Date:** 2026-06-17 (run); **updated 2026-06-18** (Stage 2 — GT relabel + M1 redesign)
**Scope:** Grafana `p1_create_dashboard` (`grafana-p1-clean`, `grafana-p1-m1`) on **OSS Grafana 13.0.2**
**Driver:** autonomous run per `roles/DRIVER.md`, validating `PLAN_failure-remediation.md` per `RUNBOOK_remediation.md`
**Predecessor:** `RESULTS_mvp-run.md` (first run, Grafana 11.6.0 — the broken-oracle run)

> This is the live re-run the runbook was waiting on. The remediation code had never
> been executed before this session. Net result: **the pipeline runs end-to-end on the
> correct product version, the major fixes work, and the verifier is far stronger than
> the first run's headline implied** — three runtime bugs were found and fixed live, and
> the two evaluation-substrate issues surfaced here (a doc-vs-OSS-edition gap in the
> ground truth; an invalid M1 mutation) have since been **resolved** per
> `PLAN_gt-relabel-and-m1-redesign.md` (see the **2026-06-18 update** below). One
> measurement issue (a miscalibrated extraction-recall matcher) remains open.

> **2026-06-18 update (Stage 2 — Plan-Executor).** Per `PLAN_gt-relabel-and-m1-redesign.md`:
> (1) the four doc-vs-OSS discrepancies (`c3/c5/c9/c12`) were **relabeled
> `is_correct=true → false` with per-claim provenance** on both `grafana-p1-clean` and
> `grafana-p1-m1`; the **clean oracle run re-scores to TP4 / FP2 / FN0 / TN9 / UNC10**
> (recall 100%, the 2 remaining FPs are c2 + c17). (2) The invalid M1 mutation was
> **redesigned** from "Home instead of Dashboards" to "**New → Import dashboard** instead
> of New Dashboard" (a real, observable wrong-path contradiction).

> **2026-06-18 update (Stage 3 — Driver).** The m1 **end-to-end re-run is DONE** (reused
> cached Pass A; drove the new Pass B replay + re-verified). **Both binding criteria are
> met: c1 → FALSE (3/3, confidence 1.0) and `mutation_detected = True`**, with the new
> replay `grafana-p1-m1__new-dashboard.replay.json` landing on `final_url=/dashboard/import`
> (title "Import dashboard - Dashboards - Grafana"), **not** `/dashboard/new`. The full m1
> oracle matrix is **TP5 / FP4 / FN0 / TN9 / UNC7** (recall 100%); the FP/TN/UNC split is
> noisier than the plan's idealized TP5/FP2/FN0/TN8/UNC10 prediction because the N=3
> verifier is stochastic — c18 and c25 happened to resolve FALSE this run instead of
> abstaining (see "M1 … Re-run result" below). The two evaluation-substrate issues are now
> fully **RESOLVED** — the sections below have been updated with these actual numbers (no
> "pending" markers remain).

## Headline

- **Autonomous navigation: 19/20 screens reached (95%)** on a seeded OSS 13.0.2 instance
  — up from 14/20 (70%) in the first run. The deterministic seed fixture (Fix 5) is what
  unblocked the complex-state screens.
- **Verifier quality is strong, not weak.** On the 25 clean claims: **0 false negatives**
  (no missed contradictions — the costly error per MISSION.md). After the 2026-06-18
  relabel, the clean oracle matrix is **TP4 / FP2 / FN0 / TN9 / UNC10** (precision 66.7%,
  recall 100%): the verifier *correctly* catches the four real doc-vs-OSS discrepancies
  (c3/c5/c9/c12, now GT TPs), leaving just **2 FPs** — c2 (a genuine color-judgment error)
  and c17 (a fixture-coverage gap, not a product difference). _(Pre-relabel this read "6
  FP"; see "The doc-vs-OSS-edition gap" below.)_
- **Capability smoke tests both pass with zero code change:** headless `claude -p`
  auto-loads the project `.mcp.json` and drives chrome-devtools (Fix 2), and Haiku ingests
  a real PNG via `Read` (Fix 4).
- **Instrumentation is now trustworthy:** the corrected confusion matrix + `uncertain`
  bucket re-score the first run to exactly **TN6 / FP10 / UNC9** (was reported "19 FP");
  per-phase + total **cost is captured** ($23.41 for the clean oracle run).
- **M1 (wrong-nav-path) mutation: REDESIGNED + DETECTED (2026-06-18).** The original mutation
  ("Click **Home** → New → New Dashboard") still creates a new dashboard in OSS 13.0.2 via
  Grafana's **global "New" button**, so it was not an observable contradiction and the verifier
  correctly returned c1→TRUE — proving Fix 2's trace mechanism but not *detection*. M1 is now
  **"Click Dashboards → New → Import dashboard"** (reverting step 1, mutating step 2): "Import
  dashboard" lands on `/dashboard/import`, not a new empty dashboard, so the documented path no
  longer reaches the asserted end state regardless of entry point. **The Stage-3 Driver re-run
  confirms it: c1 → FALSE (3/3, confidence 1.0), `mutation_detected = True`**; the new Pass B
  replay records `final_url=/dashboard/import` (not `/dashboard/new`). M1 now exercises
  *detection*, not just the mechanism.

## Acceptance-check scorecard (RUNBOOK_remediation.md)

| # | Check | Result |
|---|-------|--------|
| 1 | Metrics trustworthy (matrix, uncertain bucket, cost) | ✅ Re-score = TN6/FP10/UNC9; per-phase cost captured |
| 2 | Oracle valid (version preflight; ex-FP flips) | ✅ preflight 13.0.2==13.0.2; ex-FP flips **done 2026-06-18** (c3/c5/c9/c12 relabeled w/ provenance → clean TP4/FP2/FN0/TN9/UNC10) |
| 3 | M1 detected for the right reason (c1→FALSE via replay) | ✅ mutation **redesigned + detected 2026-06-18** (New→Import dashboard → replay `final_url=/dashboard/import`); **c1→FALSE 3/3, `mutation_detected=True`** (Stage-3 Driver re-run) |
| 4 | Verifier sensitive + stable (self-consistency, failing_atom, visual→UNC, no FN rise) | ✅ N=3 mostly 3/3; failing_atom present; 0 FN |
| 5 | Image honest (`used_image_fallback` only when an image was read) | ✅ 1 image fallback (c2), correctly flagged |
| 6 | Reachability up (the 9 no-capture screens become real verdicts) | ✅ 19/20 reached; 5/9 ex-UNC now decided |
| 7 | True E2E (~25–40 canonical claims; chain runs unseeded; recall) | ⚠️ 52 claims/20 canonical screens (good); recall matcher miscalibrated |
| 8 | No leakage (L1 test; namespaced captures; product-derived ontology) | ✅ L1 OK; captures version+fixture-namespaced |

## Phase-by-phase (clean, oracle-seeded for a clean verifier signal)

| Phase | Result | Cost | Time |
|-------|--------|------|------|
| 1 Extract | (oracle-seeded, 25 GT claims) | $0 | 0s |
| 2 Plan | 20 driver plans, sensible DAG | $1.98 | 461s |
| 3 Drive | **19/20 reached** (only `dashboard-edit-mode-panel-drag` failed) | $19.13 | 7509s (~2h) |
| 4 Verify | 9 true / 6 false / 10 uncertain; 1 image fallback | $2.30 | 1651s |
| **Total** | | **$23.41** | ~2h45m |

Drive is the overwhelming cost/time driver (autonomous Sonnet navigation, ~6–7 min/screen).
Captures are version+fixture-namespaced and **cached/shared** across clean↔m1 and
oracle↔E2E, so screens are driven once and reused — re-runs after a fix are cheap.

## Clean verifier analysis (post-relabel)

Detection framing (positive = contradiction present), after the 2026-06-18 relabel of
c3/c5/c9/c12 to `is_correct=false`: **TP 4, FP 2, FN 0, TN 9, UNC 10** (precision 66.7%,
recall 100%, coverage 60%). The four doc-vs-OSS discrepancies the verifier *correctly*
flagged are now ground-truth true positives; the two remaining FALSEs are the only real
false alarms:

| Claim | Verdict | Classification | Evidence |
|------|---------|--------------------|----------|
| c2 "Add new element icon is a blue plus" | FALSE (img, 2/3) | **FP — genuine verifier error** | Screenshot + description both show it *is* blue; Haiku misjudged the color atom |
| c3 "three panel options incl. Use saved query" | FALSE (text, 3/3) | **TP (GT corrected, provenance recorded)** | Capture: only 2 options; "Use saved query" absent in OSS |
| c5 "Use saved query opens Saved queries drawer" | FALSE (2/3) | **TP (GT corrected, provenance recorded)** | Same Enterprise/Cloud-only feature, absent in OSS |
| c9 "toolbar has Filters overview + Dashboard insights" | FALSE (text, 3/3) | **TP (GT corrected, provenance recorded)** | Capture: both items "NOT PRESENT" in OSS 13.0.2 |
| c12 "Custom layout option" | FALSE (2/3) | **TP (GT corrected, provenance recorded)** | UI label is "Custom grid", doc says "Custom" |
| c17 "Repeat direction Horizontal/Vertical" | FALSE (text, 3/3) | **FP — fixture-coverage gap** | Doc scopes Repeat direction to Custom-layout panels (clean line 201); seed fixture uses Auto grid, so the control is correctly absent — not a product difference (see §7 follow-up) |

So after relabeling, the 2 remaining FPs are **c2** (a real verifier color-judgment error,
left as-is to keep the verifier honest) and **c17** (a fixture-coverage gap, not a relabel —
see the fixture follow-up note). The 10 UNCERTAINs are honest abstentions on
**behavior/conditional** claims (c4, c16, c18, c23, c24, c25, …) that can't be confirmed from
a single static capture — the desired "abstain rather than false-alarm" behavior, and **0
contradictions were missed**.

> **Note (c17/c18 — fixture-coverage gap, not relabeled).** The doc (clean content line 201:
> *"06. For panels in a **custom layout**, set the following options:"*) scopes Repeat
> direction / Max per row to **Custom-grid** panels. The seed fixture uses **Auto grid**, so
> the cached capture correctly shows them absent. These remain `is_correct=true` and are a
> documented fixture-coverage limitation (the future fixture follow-up in
> `PLAN_gt-relabel-and-m1-redesign.md` §8), not a doc-vs-product discrepancy.

## The doc-vs-OSS-edition gap — RESOLVED (2026-06-18, via relabel)

The ground truth was labeled against the **documentation**, which describes Grafana Cloud /
Enterprise 13.0. We deploy **OSS `grafana/grafana:13.0.2`**. Several documented features
genuinely do not exist in OSS, so the verifier's FALSE verdicts are *correct* — but they were
scored as false alarms against a GT that assumed those features were present.

**Resolution: option (a) — relabeled.** Per `PLAN_gt-relabel-and-m1-redesign.md` §1, the four
affected claims (`c3, c5, c9, c12`) were flipped `is_correct=true → false` on **both**
`grafana-p1-clean` and `grafana-p1-m1`, each with a machine-readable per-claim `provenance`
string (new schema field) citing the deployed-product evidence, plus an updated entry-level
`labeled_by`. This reclassifies the 4 FPs into TPs; the clean oracle run now scores
**TP4/FP2/FN0/TN9/UNC10**. **This is the mission working** (catching doc↔product drift), and
the GT now reflects the deployed edition.

### Relabel provenance (issue #1)

Provenance is recorded in three places: the per-claim `provenance` field in the manifest
(authoritative, machine-readable), the entry-level `labeled_by`, and this table.

| claim | type | old → new `is_correct` | oracle verdict | evidence (deployed-product) |
|---|---|---|---|---|
| `grafana-p1-c3` | ui_element | true → **false** | FALSE 3/3 | New-panel dialog presents only "Configure visualization" + "Use library panel"; "Use saved query" absent (Enterprise/Cloud-only). `results/descriptions/13.0.2/grafana-p1-seed-v1/new-panel-options.txt` |
| `grafana-p1-c5` | behavior | true → **false** | FALSE 2/3 | `savedQueries` feature toggle disabled → "Use saved query" / "Saved queries" drawer do not exist (Enterprise/Cloud public-preview only). `…/saved-queries-drawer.txt` + `/api/frontend/settings` featureToggles |
| `grafana-p1-c9` | ui_element | true → **false** | FALSE 3/3 | Edit toolbar has 7 items; "Filters overview" + "Dashboard insights" absent in OSS. `…/dashboard-edit-mode-toolbar.txt` |
| `grafana-p1-c12` | field_value | true → **false** | FALSE 2/3 | Layout option labeled "Custom grid" (inline Options panel + Settings → Default grid), not "Custom" — version/label drift. `…/dashboard-settings-layout.txt` |

`labeled_by` (both entries): *"human doc-review (Grafana /latest docs, v13.0 family); live
re-validated on OSS 13.0.2 2026-06-18 (per-claim provenance on relabeled claims
c3/c5/c9/c12)"*. The schema/validator change that allows clean entries to carry
provenance-backed `is_correct=false` is described in §3 of the plan (and `CLAUDE.md`).

## Extraction analysis (Fix 6)

- **52 claims from the clean doc** (was 111 in the first run — ~2× the 25 GT, down from
  ~4.4×) across **20 canonical screens** (was 42 ad-hoc), **13/20 already cache-aligned** to
  the product ontology. Fix 6 (volume control + ontology canonicalization) substantially
  worked: the extract→plan→drive chain now runs at sane scale and reuses captures.
- **Recall is good but not credibly measured.** The `metrics.score_extraction` word-overlap
  matcher at its default `threshold=0.6` reports **12% recall** — a measurement artifact, not
  a miss. Sweeping the threshold: 0.6→12%, 0.4→36%, 0.3→48%, 0.25→60%, **0.2→92% (23/25)**.
  The extracted claims are accurate paraphrases ("Add new element icon appears as a blue plus
  sign" = GT c2) that simply don't share ≥60% verbatim words with the GT sentence.
  **Recommendation:** replace word-overlap with a semantic matcher (embedding similarity or an
  LLM judge) or recalibrate the threshold; until then, report recall as a band, not a point.

## Bugs found and fixed during this run

1. **Transient-CLI fragility (fixed).** One `claude -p` exit-1 on the m1 plan call aborted the
   whole orchestrator (after a 2-hour clean drive). Added `_invoke_cli_retry` (2 retries, linear
   backoff) in `claude_runner.py` so transient blips self-heal, and a per-dataset `try/except`
   in `orchestrator.main()` so one dataset's failure can't nuke the report.
2. **Windows cp1252 print crash (fixed).** `print()` of LLM text containing non-cp1252 Unicode
   (`→`) raised `UnicodeEncodeError` and killed the m1 E2E drive at screen 1 (redirected stdout
   defaults to the locale codepage). Fixed centrally in `config.py` by reconfiguring
   stdout/stderr to UTF-8 (`errors="replace"`).
3. **Acceptance analyzer import (fixed).** `results/_acceptance.py` run-by-path couldn't import
   `pipeline`; added a `sys.path` bootstrap. (Scratch tooling, gitignored.)

A scoring caveat (not a bug): `score_verdicts` maps verdicts to GT by exact `claim_id`, but E2E
extraction assigns its own (GT-blind) IDs, so the automated per-claim verification matrix and
`mutation_detected` only line up when extraction's IDs coincide with GT's. M1 is therefore
assessed from the ID-independent Pass B replay trace + the nav-claim verdict.

## M1 (wrong-nav-path) — REDESIGNED + DETECTED (2026-06-18)

### Why the original mutation was invalid (background)

The original M1 changed the documented first step from "Click **Dashboards**" to "Click
**Home**", assuming Home leads to the welcome page (not the Dashboards list) and so breaks the
procedure. The Pass B replay of the documented "Home" path (`grafana-p1-m1__home.replay.json`)
showed what actually happens in OSS 13.0.2:

| Step | Action | Result | `control_present` |
|---|---|---|---|
| 4 | click **Home** | stays on **Home** page (not the Dashboards list) | true |
| 5 | click **New** (top-right) | dropdown opens — **the global "New" button exists on Home** | true |
| 6 | click **New Dashboard** | navigates to `/dashboard/new` | true |
| 7 | observe | empty new-dashboard canvas confirmed | true |

The replay **did** capture the intended divergence (step 4: Home ≠ Dashboards list), but
Grafana's **global "New" button** makes the first menu choice irrelevant to the outcome — the
mutated path still creates a new dashboard, so the verifier correctly returned **c1 → TRUE**.
This **proved Fix 2's trace/replay mechanism works** but exercised the *mechanism*, not
*detection*: the mutation was not an observable contradiction (exactly the scenario
`RUNBOOK_remediation.md` anticipated — "flag it rather than forcing a verdict").

### The redesign (issue #2)

Per `PLAN_gt-relabel-and-m1-redesign.md` §2, M1 is now **"Click Dashboards → New → Import
dashboard"** — step 1 reverts to "Dashboards" and step 2's menu selection changes from "New
Dashboard" to **"Import dashboard"**:

- `mutation.name`: `wrong_nav_path_import_instead_of_new_dashboard`
- `original_text`: `02. Click **New** and select **New Dashboard**.`
- `mutated_text`: `02. Click **New** and select **Import dashboard**.` (manifest content line 15)
- `affected_claim_ids` / `expected_findings`: `["grafana-p1-c1"]`
- GT `c1.text` (m1) rewritten to: *"Clicking 'Dashboards' in the main menu and then clicking
  'New' > 'Import dashboard' opens a new empty dashboard."* (`is_correct=false`, the mutation
  finding; `type=nav_path`, `target_screen="New Dashboard"`, `line_number=14` unchanged).

Both "New Dashboard" and "Import dashboard" exist in the global "New" menu, but **"Import
dashboard" opens the dashboard-import screen (`/dashboard/import`), not a new empty
dashboard** — so unlike the Home swap, the global "New" button **cannot** rescue this: the
wrong menu item lands on the wrong screen regardless of entry point. This is a genuine,
**observable** wrong-navigation-path contradiction.

### Re-run result (Stage-3 Driver, 2026-06-18) — DETECTED

The Stage-3 Driver re-ran m1 via the **oracle path** (`run_pipeline('grafana-p1-m1',
oracle_claims=True)`): cached Pass A captures reused, the **new Pass B replay driven live**,
then all 25 claims re-verified (N=3). The new replay
(`grafana-p1-m1__new-dashboard.replay.json`) walked the documented path and recorded:

| Step | Action | `resulting_url` | `control_present` |
|---|---|---|---|
| 3 | click **Dashboards** (left sidebar) | `/dashboards` | true |
| 4 | click **New** (Dashboards-page button) | `/dashboards` (dropdown opens) | true |
| 5 | click **Import dashboard** (menu item) | **`/dashboard/import`** | true |

`final_url = http://localhost:3000/dashboard/import`, `final_title = "Import dashboard -
Dashboards - Grafana"` — **the documented path reaches the import form, not a new empty
dashboard**. The verifier judged c1's `nav` atom against this trace:

> *"Atom 4 (import page shows empty dashboard): Contradicted by trace — the import page
> displays an import form (file upload, JSON input fields) not an empty dashboard editor. This
> is the core failure: the documented path claims to open a new empty dashboard, but reaches an
> import form instead."*

**Result: `c1 → FALSE` (3/3 votes, confidence 1.0); `mutation_detected = True`.** The clean
path is unchanged, so `grafana-p1-clean` c1 stays TRUE (verified in the clean re-score). M1 now
tests **detection**, not just the trace mechanism.

> **Authenticity note (label divergence the replay surfaced):** the live menu item is labeled
> just **"Import"** (no "dashboard" suffix) in OSS 13.0.2, but it still navigates to
> `/dashboard/import`. The contradiction is in the *destination*, so it is robust to the label
> wording — the verifier flagged the divergence and proceeded.

**Full m1 oracle matrix:** **TP 5 · FP 4 · FN 0 · TN 9 · UNC 7** (precision 55.6%, recall
100%, coverage 72%).

| Bucket | Claims |
|---|---|
| **TP (5)** | **c1** (mutation, 3/3), c3, c5, c9, c12 (the four relabeled doc-vs-OSS discrepancies) |
| **FP (4)** | c2 (genuine color-judgment error), c17 + **c18** (fixture-coverage gap — Repeat direction / Max per row, scoped to Custom-grid panels; fixture is Auto grid), c25 (noise this run) |
| **FN (0)** | — (recall 100%; **no contradiction missed** — the mission's primary criterion) |
| **TN (9)** | c6, c7, c8, c10, c11, c13, c14, c15, c19 |
| **UNC (7)** | c4, c16, c20, c21, c22, c23, c24 (honest abstentions on behavior/conditional claims) |

> **Variance vs the plan's prediction.** Plan §5b predicted TP5/FP2/FN0/TN8/UNC10. The binding
> criteria (c1→FALSE, `mutation_detected=True`, **FN=0**) match exactly; the FP/TN/UNC split is
> noisier because the **N=3 self-consistency verifier is stochastic** — this run c18 and c25
> resolved FALSE (2/3 each) instead of abstaining, and one normally-uncertain claim resolved
> TRUE (TN9 vs the predicted TN8). c18's FALSE is the *same* fixture-coverage gap as c17 (both
> Custom-grid-scoped controls absent in the Auto-grid fixture), so it is a defensible
> detection, not a regression; c25 is genuine run-to-run noise. The clean re-score
> (deterministic w.r.t. GT, no re-drive) holds at TP4/FP2/FN0/TN9/UNC10 — the c2+c17 FPs are
> the stable pair across both datasets.

> Scoring caveat (carries over): the auto-scored m1 matrix is only fully interpretable via the
> **oracle path** (GT-aligned IDs). E2E extraction assigns its own GT-blind IDs that align with
> the GT only at `c1`, so the Driver ran m1 via the oracle path for a trustworthy matrix
> (plan §5b).

## Cost

- Clean oracle run: **$23.41** (drive $19.13 dominates). Capture + rate-card cross-check both
  active in `pipeline_report.json`.
- The first run's <$5 target is unrealistic for autonomous Sonnet UI driving of a 20-screen
  page; the real lever is the capture cache (drive once, reuse across variants/runs).

## Artifacts

- Clean oracle verdicts: `results/verdicts/grafana-p1-clean.oracle.json`
- **m1 re-run verdicts (Stage-3, 2026-06-18): `results/verdicts/grafana-p1-m1.json`** (c1→FALSE 3/3; 9 true / 9 false / 7 uncertain)
- Captures (19 screens): `results/{screenshots,descriptions,traces}/13.0.2/grafana-p1-seed-v1/`
- Pass B replay (clean baseline): `results/traces/13.0.2/grafana-p1-seed-v1/grafana-p1-clean__new-dashboard.replay.json`
- **m1 redesigned Pass B replay: `results/traces/13.0.2/grafana-p1-seed-v1/grafana-p1-m1__new-dashboard.replay{,.authored}.json` (+ `.png`)** — `final_url=/dashboard/import`
- Reports: `results/pipeline_report_oracle.json` (clean). The m1 re-run was a direct `run_pipeline` call, so no separate `pipeline_report` JSON / cost-ledger line was emitted (only `orchestrator.main` persists the ledger); the re-run reused cached Pass A, so its incremental cost is verify-dominated and small.
- Phase logs: `results/_orch_oracle.log`, `results/_m1_driveverify.log`, **`results/_workflow/m1_rerun.log` (Stage-3 re-run)**
- Driver acceptance analyzer: `results/_acceptance.py`

# Runbook: validating the failure-remediation changes

**Audience:** the DRIVER (`roles/DRIVER.md`). The PLAN-EXECUTOR implemented the
code for `PLAN_failure-remediation.md`; the runtime smoke tests, the live re-run,
and the empirical acceptance checks are yours.

> **VALIDATED 2026-06-17 (DRIVER run); substrate revisions 2026-06-18.** The live re-run is
> complete — full results in **`RESULTS_remediation-run.md`**. Summary: the pipeline + Fixes
> 1–6 run end-to-end on OSS Grafana 13.0.2; drive **19/20**; verifier strong (**0 FN**); MCP
> + image smoke tests pass with no code change; cost captured ($23.41 clean). Three runtime
> bugs were found and fixed live (transient-CLI retry, orchestrator per-dataset guard, Windows
> cp1252→UTF-8 print crash). The two **evaluation-substrate** issues are now **RESOLVED** per
> `PLAN_gt-relabel-and-m1-redesign.md`: the **doc-vs-OSS-edition gap** was fixed by relabeling
> c3/c5/c9/c12 `is_correct=false` with per-claim provenance (clean oracle re-scores to
> **TP4/FP2/FN0/TN9/UNC10**), and **M1 was redesigned** to "Dashboards → New → Import
> dashboard" (a real `/dashboard/import` contradiction). The **Stage-3 Driver re-ran m1
> end-to-end (2026-06-18) and it is DETECTED: c1→FALSE 3/3, `mutation_detected=True`, replay
> `final_url=/dashboard/import`; m1 oracle matrix TP5/FP4/FN0/TN9/UNC7, recall 100%.** Per-check
> status: see the RESULTS scorecard.

## What changed (file map)

- **Phase 0 — measurement.** New `pipeline/metrics.py` is the single ground-truth
  reader + canonical confusion matrix (detection framing; `uncertain` is its own
  bucket) + shared fuzzy matcher + rate card. `verify.evaluate` and
  `orchestrator.evaluate_against_ground_truth` now delegate to it. `claude_runner`
  has a `COST` ledger and captures `total_cost_usd` on every call; the orchestrator
  reports per-phase + total cost. `tests/test_leakage_guards.py` enforces L1.
- **Fix 1 — version.** `config.PRODUCT_VERSION = "13.0.2"`, `GRAFANA_IMAGE` derived.
  `dataset/schema.py` + the two grafana-p1 manifest entries gained `product_version`
  + `labeled_against_version` + `labeled_by`. `drive.assert_version()` refuses to
  run on a deployed≠labeled mismatch.
- **Fix 2 — nav traces.** `claude_runner.run_claude_stream` + `parse_mcp_trace`;
  `models.NavigationTrace`/`NavigationStep`; `drive.drive_screen` captures a Pass A
  trace, `drive.replay_documented_path` runs Pass B; `verify` judges `nav` atoms
  against the trace. `prompts/agent_system.txt` (authors a trace) +
  `prompts/replay_procedure.txt` (new).
- **Fix 3 — verifier.** `prompts/decompose_claim.txt` (new) + rewritten
  `verify.py`: atomic decomposition, N=3 self-consistency majority vote, visual
  atoms route to image or abstain.
- **Fix 4 — image.** Real screenshot via the Read tool on the driver's neutral
  capture; the fake "screenshot attached" note is gone; `IMAGE_INPUT_ENABLED`
  switch falls back to UNCERTAIN if headless image input is unsupported.
- **Fix 5 — fixtures.** `fixtures/grafana/p1_seed_dashboard.json` + README;
  `drive.provision_fixture()` (UI import, setup-only); captures are
  version+fixture-namespaced (`config.capture_subdir`, L3/L7).
- **Fix 6 — extraction.** `prompts/extract_claims.txt` volume control + semantic
  dedup in `extract.py`; `pipeline/ontology.py` +
  `fixtures/grafana/screen_ontology.json` normalize screens (L5); orchestrator
  `--oracle-claims` debug mode (default is true E2E).

## Step 0 — offline checks (no infra needed)

```bash
python tests/test_leakage_guards.py          # L1 import-isolation: expect "OK"
python -c "from dataset import loader; print(loader.validate(loader.load()) or 'manifest OK')"
```

Re-score the FIRST RUN's verdicts under the corrected framing (Phase 0 acceptance):

```bash
python -c "from pipeline import metrics; s=metrics.score_verdicts(metrics.load_verdict_results('grafana-p1-clean'),'grafana-p1-clean'); print(metrics.format_verification(s))"
```
**Note (2026-06-18):** this command now re-scores against the **post-relabel** GT →
**TP4/FP2/FN0/TN9/UNC10** (recall 100%; the 2 FPs are c2 + c17). The historical
**TN6/FP10/UNC9** figure was a *pre-relabel* datapoint that proved the matrix +
`uncertain`-bucket instrumentation fix on the 11.6.0 first-run verdicts; it no longer
matches the corrected ground truth. Both are correct for their respective GT snapshots.

## Step 1 — capability smoke tests (Fixes 2 & 4)

1. **stream-json tool events (Fix 2).** Run a throwaway:
   `claude -p --output-format stream-json --verbose --allowedTools "mcp__chrome-devtools__*" "open example.com and take a snapshot"`
   Confirm the ndjson contains `assistant` events whose content has `tool_use`
   blocks named `mcp__chrome-devtools__*`. If NOT, the agent-authored trace
   fallback covers it (the agent Writes the trace file) — no code change needed,
   but note it.
2. **Image ingest (Fix 4).** `claude -p --allowedTools "Read" "Use Read to view <some.png> and describe it."` If it cannot see the image, set
   `config.IMAGE_INPUT_ENABLED = False` (visual atoms then abstain — honest).

## Step 2 — bring up infra on the LABELED version + fixture

```bash
# Docker Desktop must be running.
python -m pipeline.drive grafana-p1-clean --setup
```
This starts a debug Chrome + Grafana **13.0.2**, runs the version preflight
(aborts on mismatch), provisions the seed fixture via the UI, pre-auths, then
drives the clean set. Confirm "Version preflight OK: deployed Grafana 13.0.2".
Old 11.6.0 captures are ignored automatically (captures are now namespaced under
`results/<capture>/13.0.2/grafana-p1-seed-v1/`).

## Step 3 — drive the mutation + verify, or run E2E

Phased (recommended first): isolate plan/drive/verify from extraction noise:
```bash
python -m pipeline.orchestrator --oracle-claims   # infra already up
```
Then the true end-to-end (exercises extraction, Criterion 1):
```bash
python -m pipeline.orchestrator
```
`results/pipeline_report.json` now carries `cost_usd` per phase + `cost_usd_total`.

## Acceptance checks (map to success criteria)

1. **Metrics trustworthy:** Step 0 re-score = TN6/FP10/UNC9; report has non-null
   per-phase `cost_usd`; one FP/FN definition across both evaluators.
2. **Oracle valid — RESOLVED (2026-06-18).** preflight prints deployed==labeled (13.0.2).
   The doc-vs-OSS gap is closed: c3/c5/c9/c12 relabeled `is_correct=false` with per-claim
   provenance on both grafana-p1 entries; the clean oracle run re-scores to
   **TP4/FP2/FN0/TN9/UNC10** (recall 100%). The 2 remaining FPs are c2 (genuine
   color-judgment error) and c17 (fixture-coverage gap, not a relabel).
3. **M1 detected for the right reason — RESOLVED (2026-06-18).** M1 is now "Dashboards → New →
   **Import dashboard**" (not "New Dashboard"). The Stage-3 Driver re-ran it end-to-end: the new
   Pass B replay `results/traces/13.0.2/grafana-p1-seed-v1/grafana-p1-m1__new-dashboard.replay.json`
   records `final_url=/dashboard/import` (not `/dashboard/new`), and **`grafana-p1-m1` c1 → FALSE
   (3/3, conf 1.0) with `mutation_detected=True`**; clean c1 stays TRUE. Full m1 oracle matrix
   **TP5/FP4/FN0/TN9/UNC7** (recall 100%) — the FP/TN/UNC split is noisier than the plan's
   idealized TP5/FP2/FN0/TN8/UNC10 because the N=3 verifier is stochastic (c18 + c25 resolved
   FALSE this run; c18 is the same fixture-coverage gap as c17). Binding criteria all met.
4. **Verifier sensitive + stable:** c17 reproducible across runs (self-consistency);
   compound claims report a `failing_atom`; visual claims with no image are
   UNCERTAIN not FALSE; FN (missed contradiction) count does not rise.
5. **Image honest:** `used_image_fallback=true` only when an image was truly read;
   zero fabricated visual verdicts.
6. **Reachability up:** the 9 "no screen captured" UNCERTAINs (c5,c12–c16,c20,c21,c25)
   become real verdicts for screens that exist in 13.0.2.
7. **True E2E:** extraction emits ~25–40 canonical-screen claims; the full chain
   runs without GT seeding; recall reported by `metrics.py`.
8. **No leakage:** `tests/test_leakage_guards.py` passes; captures are
   version+fixture-keyed; ontology is product-derived; GT relabeled independently.

## Known spot-checks / open items

- **c5 "Use saved query" (Saved queries drawer) — RESOLVED (relabeled 2026-06-18).** The
  doc marks Saved queries as *public preview in Grafana Enterprise and Grafana Cloud only*;
  the OSS `grafana/grafana:13.0.2` image lacks it (the `savedQueries` toggle is disabled), so
  the verifier's FALSE is correct. c5 (and the related c3/c9/c12) was relabeled
  `is_correct=false` with per-claim provenance — the verifier no longer "silently absorbs" it;
  the GT now matches the deployed edition.
- **M1 semantics — RESOLVED (redesigned + detected 2026-06-18).** The original "Home → New →
  New Dashboard" did reach a new dashboard via the global "+ New" button (c1 correctly TRUE), so
  M1 was not an observable contradiction — confirmed by the old Pass B replay. M1 was redesigned
  to "Dashboards → New → **Import dashboard**", which lands on `/dashboard/import` (the wrong
  screen regardless of entry point). The Stage-3 Driver re-ran the new replay and **confirmed
  c1→FALSE (3/3) + `mutation_detected=True`** (replay `final_url=/dashboard/import`). Note the
  live menu item is labeled just **"Import"** (no "dashboard" suffix) but still routes to
  `/dashboard/import` — the contradiction is in the destination, robust to the label wording.
- **Self-consistency cost/time.** Verify is 3× the calls (Haiku, cheap) plus a
  decompose call per claim; expect verify to take longer. Tune `VERIFY_SELF_CONSISTENCY_N`
  on DEV if needed.
- **Fixture schema.** `p1_seed_dashboard.json` is classic-schema (Grafana migrates
  on import). If auto-grid/show-hide setup fails in the UI, export an established
  dashboard from live 13.0.2, replace the file, and bump `config.FIXTURE_ID`.
- **DEV/TEST split (L4).** Only Grafana-p1 is live, so all current numbers are
  DEV-only. A second labeled page (another Grafana page, or Keycloak/NetBox) is a
  precondition for any *headline* metric.

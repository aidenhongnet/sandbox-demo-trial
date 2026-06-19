# MVP Pipeline — First End-to-End Run Results

**Date:** 2026-06-17
**Scope:** Grafana `p1_create_dashboard` (`grafana-p1-clean`, `grafana-p1-m1`)
**Driver:** autonomous run per `roles/DRIVER.md`

> **Correction (post-analysis, 2026-06-17).** The "verification is the weak link"
> framing below was **wrong on the dominant cause**. A root-cause analysis found the
> real problems were (1) a **broken oracle** — the run drove Grafana **11.6.0** while
> the doc describes **13.0's Dynamic Dashboards**, so most "false positives" were
> *correct drift detections against an invalid ground truth* — and (2) **broken
> instrumentation** (inverted FP/FN labels, `uncertain` counted as FP, no cost
> capture, prose nav-logs instead of action traces, a fake image path). The verifier
> had genuine defects too (over-strict compounds, non-determinism, visual-from-text),
> but they were secondary. See `PLAN_failure-remediation.md` for the full analysis and
> `RUNBOOK_remediation.md` for the fixes (now implemented, pending live re-run). The
> original run notes below are preserved as the historical record.
>
> **Forward pointer (2026-06-18).** The remediation was validated live on OSS Grafana
> 13.0.2, and the two evaluation-substrate issues it surfaced were then **resolved**: the
> **doc-vs-OSS-edition gap** (relabeled c3/c5/c9/c12 with provenance → clean oracle
> TP4/FP2/FN0/TN9/UNC10) and the **invalid M1 mutation** (redesigned to "New → Import
> dashboard"; the Stage-3 Driver re-run now **detects it — c1→FALSE 3/3,
> `mutation_detected=True`**, replay → `/dashboard/import`; m1 oracle TP5/FP4/FN0/TN9/UNC7,
> recall 100% — contrast the "Missed (c1 → TRUE 0.92)" row below). See
> `RESULTS_remediation-run.md` and `PLAN_gt-relabel-and-m1-redesign.md`.

## Headline

The pipeline **runs end-to-end on real infrastructure** and the **core hypothesis is
validated**: an AI agent autonomously navigated a real Grafana 11.6.0 UI from high-level
plans, reaching **14/20 screens (70%)**. The numbers below were read as "verification is
the weak link," but see the correction above: the oracle (wrong product version) and the
evaluator instrumentation were the dominant failures; clean "false-flags" were largely
correct drift detections, and the M1 miss was structural (destination-only capture).

## Methodology note (important)

To get a clean ~20-screen drive at the intended scale, Phase 2/3/4 were run from the
**25 ground-truth claims** (canonical screen names) rather than from Phase-1 extraction
output. Reason: extraction over-produces (see below), yielding 42 ad-hoc screen names that
match the navigation dependency graph only 2/42 — driving those would be hours of
un-cached navigation. The real extracted claims are preserved at
`results/claims/grafana-p1-clean.extracted.json`. For the M1 run, the mutation
(`Dashboards`→`Home`) was injected into the `c1` claim text to mirror the mutated doc,
since seeding bypasses extract-from-mutated-doc.

## Environment / infrastructure resolved this run

- **MCP server**: switched `.mcp.json` from `bunx --bun chrome-devtools-mcp` to
  `npx -y chrome-devtools-mcp@latest --browser-url=http://127.0.0.1:9222`.
  `bunx` is not installed on this machine (only `bun.exe`); node 22.14 + npx 10.9 are.
  The previous config also used a `CHROME_CDP_URL` env var the package ignores — the real
  connection flag is `--browser-url`.
- **drive.py allowed-tools**: `mcp:chrome-devtools` → `mcp__chrome-devtools__*` (the old
  colon form is not a valid `--allowedTools` token; the spawned agents would get no MCP tools).
- **Chrome CDP**: `start_chrome()` now launches with a dedicated `--user-data-dir`
  (`results/chrome-profile`) so a debuggable instance starts even when the user's normal
  Chrome is already running. Added `CHROME_USER_DATA_DIR` to `config.py`.
- Verified present: `claude` 2.1.179, Docker (daemon up), Chrome, Python 3.13 + pydantic 2.12.
- Base `claude -p` overhead ~8–11s/call; the MCP health-check is **not** a latency bottleneck.

## Phase-by-phase

| Phase | Result | Notes |
|-------|--------|-------|
| 1 Extract | Runs | 111 claims from p1 (vs 25 GT) — **over-extracts ~4.4×**; emits 42 ad-hoc screen names (2/42 match the nav graph). Per-claim quality looks reasonable; problem is quantity + inconsistent screen naming. The standalone `extract.py` evaluator uses exact lowercased string-equality → reports 0% recall (misleading; an LLM paraphrase never matches verbatim). |
| 2 Plan | Works | 20 driver plans from GT claims, sensible dependency DAG; 17/20 screens match `GRAFANA_P1_DEPS` → caching/branching effective. ~7 min. |
| 3 Drive | **14/20 (70%)** | Chrome CDP + chrome-devtools MCP + Grafana + `claude -p` all integrate; pre-auth succeeded. Agent honestly reports failure (writes no files) instead of fabricating. ~1h40m. |
| 4 Verify | Poor | Text-only against agent descriptions. 16 decided / 9 uncertain; **6/16 correct (37.5%)**; **10/25 good claims wrongly flagged FALSE**. M1 missed. |

### Drive detail (14 reached / 6 failed)

Reached: new-dashboard, new-dashboard-edit-mode, new-panel-options, panel-edit-mode,
panel-edit-mode-queries-tab, panel-edit-mode-visualization-picker, dashboard-edit-mode-toolbar,
dashboard-view-mode-toolbar, dashboard-sidebar, dashboard-edit-mode-save-menu,
panel-sidebar-repeat-options, panel-sidebar-showhide-rules, dashboard-edit-mode-panel-drag,
dashboard-edit-mode-panel-resize.

Failed: saved-queries-drawer, dashboard-settings-layout, content-outline,
showhide-rules-template-variable-rule, showhide-rules-match-rules (all require complex
dashboard state that doesn't exist in a fresh instance) + auto-grid-layout-settings
(cascade-skipped after its parent dashboard-settings-layout failed).

## Success-criteria scorecard (from PLAN_mvp-pipeline.md)

| # | Criterion | Target | Result | Verdict |
|---|-----------|--------|--------|---------|
| 1 | Extraction recall | ≥80% | Not cleanly measurable (exact-match evaluator → 0%; over-extraction). Bypassed via GT seeding. | ⚠️ Inconclusive |
| 2 | Navigation success | ≥70% | **70% (14/20)** | ✅ Met |
| 3 | Clean false-positives | ≤2 | **10** good claims flagged FALSE | ❌ Not met |
| 4 | Detect M1 mutation | yes | **Missed** (c1 → TRUE 0.92) | ❌ Not met |
| 5 | Total cost | <$5 | Est. ~$2–4 (not precisely tracked) | ⚠️ Likely met, unverified |

## Key findings

1. **Autonomous navigation works** (the central unknown). 70% on a fresh Grafana, with
   honest failure reporting. Failures concentrate on screens needing pre-existing complex
   state (variables, multiple rules, custom layouts) — a fixture/seeding problem, not a
   navigation-capability problem.

2. **nav_path claims can't be verified from destination screen states.** c1 ("click
   **Home** … opens a new dashboard") verified TRUE because the destination *is* a new
   dashboard and a "Home" sidebar item exists — the captured end-state doesn't encode the
   route taken. Detecting wrong-path mutations needs capture of the **navigation action
   sequence**, not just the final screen.

3. **The verifier conflates "can't confirm from text" with "false."** It returns
   high-confidence FALSE on compound claims when any sub-part isn't fully spelled out in
   the agent's text description (e.g., confirmed the blue "+" exists but still returned
   FALSE on a labeling nuance). It should decompose compound claims and lean UNCERTAIN on
   partial evidence.

4. **The "image fallback" never sends an image.** `verify.py` only appends a text note;
   `claude_runner.run_claude()` has no image input. visual_state claims get no real visual
   check.

5. **Eval bug fixed.** `verify.evaluate()` reported "Matched findings" by checking whether
   the expected claim appeared in the error lists — so a *missed* mutation showed as
   "matched." Now reports `Mutation detected` based on an actual FALSE verdict.

6. **Cost isn't aggregated.** `run_claude()` captures `total_cost_usd` per call but the
   orchestrator discards it. Criterion #5 can't be verified precisely.

## Recommended next steps (priority order)

1. **Capture navigation traces** (the MCP tool-call sequence / intermediate screens) so
   nav_path claims are verifiable — this is what's needed to catch M1-class mutations.
2. **Improve the verify prompt**: decompose compound claims; return UNCERTAIN (not FALSE)
   when the description is silent; calibrate confidence.
3. **Add real image input** to the fallback path (needs `run_claude` image support) for
   visual_state / ui_element claims.
4. **Tune extraction** to emit fewer claims with canonical screen names (align to the
   dependency graph) so the *real* extract→plan→drive chain runs at sane scale/cost.
5. **Seed test fixtures** (a dashboard with variables, rules, panels) so complex screens
   are reachable; raises navigation coverage above 70%.
6. **Aggregate `cost_usd`** in the orchestrator report.
7. Replace `extract.py`'s exact-match evaluator with the orchestrator's fuzzy matcher.

## Artifacts

- Screenshots/descriptions: `results/screenshots/`, `results/descriptions/` (14 each)
- Verdicts: `results/verdicts/grafana-p1-{clean,m1}.json`
- Plans: `results/plans/grafana-p1-clean.json`
- Raw extraction (111 claims): `results/claims/grafana-p1-clean.extracted.json`
- Phase logs: `results/_drive_clean.log`, `results/_verify_*.log`, `results/_plan_clean.log`

# WORKFLOW — Run the full experiment (autonomous, gated, product-sharded chain)

You are the **ORCHESTRATOR**. Your job is **not** to plan, label, edit, or drive yourself — it is
to launch role subagents **in order**, gate each stage on the previous one's success, track
progress across a long multi-product run, relay status, and produce a final report. Run from the
repository root (CWD). Continuously honor `MISSION.md` and `CLAUDE.md`.

---

## Objective

Scale the pipeline from the **validated Grafana-`p1` smoke test** to the **full experiment**
defined by `MISSION.md` + `dataset-plan.md`, and produce the headline research metrics. The
pipeline code (`pipeline/`) is proven end-to-end on one page; the work now is **breadth**: author
the rest of the ground-truth dataset, generalize the Grafana-specific code to all three products,
run the whole dataset through the four phases, and score it honestly.

This is too large for one pass. Carry it out as a **gated chain, sharded per product, and
resumable**: a one-time **Planner** stage, then for each product a **Builder** (Plan-Executor)
followed by a **Driver**, then a one-time **Analyst** (Driver) stage that aggregates the headline
metrics. Every stage is one autonomous `claude -p` process; you gate, checkpoint, and relaunch.

---

## What "the full experiment" is (the target — do not let the Planner shrink it silently)

Per `dataset-plan.md`, scoped against the **deployed** product builds (not doc-assumed editions):

- **3 products**: Grafana, Keycloak, NetBox — three doc formats (Markdown, AsciiDoc, RST/MkDocs),
  three domains, three UI patterns. Source docs for **all 15 pages already exist** under
  `dataset/sources/<product>/`; only `grafana-p1` is labeled in `dataset/manifest.jsonl`.
- **~15 clean pages** (5 per product) with human-grade ground truth: every verifiable claim, its
  `type` (`nav_path|ui_element|field_value|behavior|visual_state`), `target_screen`, and
  `is_correct` labeled **against the deployed build** with `provenance` for any non-mutation
  false claim (L6).
- **The mutation matrix** (M1–M7), ~87 mutations total, distributed per the `dataset-plan.md`
  sample-size table. Each injected mutation must produce an **observable** contradiction in the
  deployed product (the lesson of the M1 redesign — a "wrong path" that still reaches the intended
  end state tests nothing).
- **Headline metrics** (`dataset-plan.md` → Metrics; `pipeline/metrics.py` is the only scorer):
  extraction recall, **FP rate on clean pages**, **FN rate per mutation type** (the priority —
  `MISSION.md`: missed contradictions are the costly error), navigation success, attribution
  accuracy. Reported with a real **DEV/TEST split** (L4), not DEV-only.

**Success = the full dataset runs through all four phases on correctly-pinned infra, scored by the
canonical evaluator, with a held-out TEST split and per-mutation-type FN rates** — i.e. the
experiment `MISSION.md` describes, not a single-page demonstration.

---

## Current state (verify before planning — treat as input, not truth)

- **Validated**: `pipeline/` runs E2E on **Grafana 13.0.2**, `grafana-p1` only (clean + m1); drive
  19/20; verifier strong (0 FN); cost captured. See `RESULTS_remediation-run.md`,
  `PLAN_gt-relabel-and-m1-redesign.md`, and the `CLAUDE.md` status block.
- **Missing dataset**: 14 of 15 pages are unlabeled; the M1–M7 matrix is unbuilt except `grafana-p1-m1`.
- **Grafana-hardcoded code**: `orchestrator.main()` (literal `dataset_ids`), `plan.py`
  (`GRAFANA_P1_DEPS`), `config.py` (single `PRODUCT_VERSION`/image/URL/creds/`FIXTURE_ID`),
  one ontology (`fixtures/grafana/screen_ontology.json`), one fixture. All must become per-product.
- **Infra**: Grafana up (`grafana/grafana:13.0.2`). **Keycloak** (`quay.io/keycloak/keycloak
  start-dev`, admin-bootstrap env) and **NetBox** (Compose: Postgres + Redis) are **not** built —
  each needs a pinned version + a generalized `drive.assert_version()` preflight.
- **Measurement debt**: extraction-recall matcher miscalibrated (open item #3); E2E claim-ID
  scoring caveat (#4); no real DEV/TEST split yet (L4). These gate *trustworthy* headline numbers
  and are in scope for the Planner.

---

## The problem to solve (GENERAL — pass to the Planner as written; let it derive the specifics)

> The verification pipeline is validated on a single Grafana page. Scale it to the full experiment
> in `MISSION.md` + `dataset-plan.md`. **Investigate the current repo, the manifest, the existing
> source docs, the latest results, and the live products, and derive the specifics yourself from
> the evidence** — do not assume, and treat any prior write-up (including this file's "current
> state") as input to verify, not as the answer.
>
> Decide and sequence: (1) **dataset authoring** — which pages and how many of each mutation type
> per product to hit the `dataset-plan.md` matrix, and how to label ground truth against the
> *deployed* build with provenance; (2) **pipeline generalization** — what must become per-product
> (config/versions/images/URLs/credentials/infra bring-up, screen ontologies, fixtures,
> dependency graphs, and the orchestrator's dataset iteration) and how to do it without breaking
> the leakage guards; (3) **per-product infra** — pinned versions + preflights for Keycloak and
> NetBox; (4) **measurement** — fix the extraction-recall matcher and the E2E scoring caveat, and
> define a **DEV/TEST split** so headline numbers aren't DEV-tuned; (5) **run + analysis** order.
>
> Constraints (non-negotiable — carry them into the plan):
> - **Leakage guard (L1):** only `metrics.py` reads `is_correct`/`expected_findings`/`mutation`/
>   `provenance`. Prediction modules stay GT-blind; `tests/test_leakage_guards.py` must keep passing.
> - **Version pinning:** every entry's deployed build == its labeled version; generalize the
>   drive-time preflight so no product floats its image tag.
> - **Observable mutations:** every injected mutation must be a real, detectable contradiction in
>   the deployed product.
> - **Provenance (L6):** any non-mutation `is_correct=false` (real doc-vs-product drift) carries a
>   per-claim `provenance` string; `is_correct` stays decoupled from `is_mutated`.
> - **FN-priority (`MISSION.md`):** minimize and report missed contradictions per mutation type.
> - Keep changes minimal and idiomatic; reuse the Grafana path as the template; prefer re-score
>   over re-run where outputs already exist; update all results/docs you touch.

---

## Global rules (apply to every stage)

1. **Sequential & gated.** Launch stage N+1 **only if** stage N reports `SUCCESS`. Never run two
   subagents at once — they share the git working tree, Chrome, and the product containers.
2. **Product-sharded.** Process products **one at a time** (Grafana → Keycloak → NetBox; finish
   Grafana, whose `p1` is partly done, first). A product's Driver must be `SUCCESS` before the next
   product's Builder starts. This bounds each subagent's context and makes failures local.
3. **Resumable.** The run spans many hours/sessions. Maintain `results/_workflow/PROGRESS.md` (the
   ledger). On (re)launch, **read it first** and resume at the first incomplete stage — do not redo
   completed ones. A subagent that approaches its context limit must checkpoint into `PROGRESS.md`
   and report `BLOCKED — context`; you then relaunch it to continue (see classification).
4. **Autonomous, no interruptions.** Each subagent runs end-to-end on best-judgment recommendations
   and must **not** pause for confirmation. Reserve `BLOCKED` for a hard external blocker (or a
   context checkpoint) it genuinely cannot resolve itself.
5. **Each subagent is one headless `claude -p` process**, launched with **opus 4.8**,
   **`--dangerously-skip-permissions`**, **max effort**, and `--output-format json`, from CWD.
6. **Long-running:** launch each with the Bash tool using `run_in_background: true` and wait for the
   completion notification before classifying it (a Driver stage can run hours).
7. **Capture feedback three ways:** process exit code, the JSON envelope (`is_error`, `result`,
   `total_cost_usd`), and the stage's `*.status` file. Classify, then gate.
8. **Invariants are not the subagent's to relax.** If any subagent proposes weakening L1, the
   version preflight, provenance, or the DEV/TEST split, treat it as `BLOCKED` and surface it.

---

## Progress ledger (resumability)

Maintain one ledger the whole run keys off of:

```bash
mkdir -p results/_workflow
# results/_workflow/PROGRESS.md — orchestrator-owned checklist, e.g.:
#   - [x] 01-plan
#   - [x] 02-grafana-build
#   - [ ] 03-grafana-drive   <-- resume here
#   - [ ] 02-keycloak-build
#   ...
```

Each stage also writes the triple `results/_workflow/<STAGE>.{status,json,err}` (status authoritative).
Stage IDs: `01-plan`, then per product `02-<product>-build` and `03-<product>-drive`
(`<product>` ∈ `grafana|keycloak|netbox`), then `04-analyze`. On start, parse `PROGRESS.md` and
jump to the first unchecked stage; tick a box only after that stage classifies `SUCCESS`.

---

## Launch template (adapt `STAGE`, `ROLE`, and the task per stage)

```bash
STAGE=01-plan             # then 02-grafana-build, 03-grafana-drive, 02-keycloak-build, ... 04-analyze
ROLE=PLANNER              # then PLAN-EXECUTOR (build), DRIVER (drive + analyze)
: > "results/_workflow/$STAGE.status"

claude -p --dangerously-skip-permissions --model claude-opus-4-8 --output-format json \
  --append-system-prompt "Operate at MAXIMUM effort and deepest reasoning. Work fully autonomously end-to-end: at every fork pick the best reasonable option per MISSION.md/CLAUDE.md and proceed — do NOT stop to ask for confirmation or permission. Honor the workflow invariants (L1 leakage guard, version pinning, observable mutations, provenance, FN-priority, DEV/TEST split). If you approach your context limit, checkpoint your progress into results/_workflow/PROGRESS.md and the relevant results files, then report BLOCKED with reason 'context'. When you finish (or truly cannot proceed) do BOTH: (1) write ONE line to results/_workflow/$STAGE.status that is exactly 'SUCCESS', 'FAILED', or 'BLOCKED' followed by ' — <one-line reason>'; (2) end your final message with that same line prefixed 'WORKFLOW_STATUS: '. Use BLOCKED only for a hard external blocker you cannot resolve, or a context checkpoint." \
  > "results/_workflow/$STAGE.json" 2> "results/_workflow/$STAGE.err" <<'PROMPT'
Assume the <role> role defined in roles/<ROLE>.md.
First read results/_workflow/PROGRESS.md and resume from where the run left off.
<stage-specific task — see below>
PROMPT
echo "exit=$? stage=$STAGE"
```

> If the environment exposes an effort/thinking-budget flag or env var, set it to maximum too;
> otherwise opus 4.8 plus the "maximum effort" directive conveys it. Feed the prompt on **stdin**
> (heredoc) — `claude -p` reads the prompt from stdin. On a **relaunch** (FAILED, or BLOCKED for
> context), append the prior `*.err` tail / checkpoint pointer to the prompt so it self-corrects or
> resumes.

---

## Stage 1 — Planner  (`roles/PLANNER.md`) — run once

**Task to embed in the prompt:**
> Plan the full experiment described in this workflow's "problem to solve" section. Assess the repo,
> the manifest, the 15 existing source docs, the latest results, and the live products first; derive
> the dataset matrix, the pipeline-generalization surface, the per-product infra, the measurement
> fixes, and the DEV/TEST split from the evidence. Produce a **phased, product-sharded** plan
> (Grafana → Keycloak → NetBox, then aggregate) that respects every invariant. Recommend a concrete
> DEV/TEST split (default recommendation: DEV = Grafana + Keycloak, TEST = NetBox held out and run
> once with the judgment-bearing knobs frozen — extraction/verify prompts, the semantic matcher,
> ontology heuristics, confidence thresholds; mechanical per-product enablement like image tag, URL,
> credentials, and fixture is still allowed for the TEST product). Write the plan to `PLAN_<task>.md`.

**Deliverable:** a new `PLAN_*.md` in CWD covering all five workstreams + the run order.
**SUCCESS criteria:** the `PLAN_*.md` exists, names the dataset matrix / generalization surface /
infra / measurement fixes / DEV-TEST split, and `*.status` = `SUCCESS`.

## Stage 2 — Builder per product  (`roles/PLAN-EXECUTOR.md`) — loop: grafana, keycloak, netbox

**Task to embed in the prompt (substitute `<product>`):**
> Execute the Planner's plan (newest `PLAN_*.md` — read it first) **for `<product>` only**. Author
> that product's dataset entries — clean ground truth for its 5 pages (claims, types, target
> screens, `is_correct` labeled against the deployed build, `provenance` for non-mutation false
> claims) plus its share of the M1–M7 matrix as **observable** contradictions — and append them to
> `dataset/manifest.jsonl`. Generalize the pipeline so `<product>` is a first-class target: its
> config/version/image/URL/credentials, screen ontology, fixture, dependency graph, and the
> orchestrator's dataset iteration — reusing the Grafana path as the template and keeping
> `metrics.py` the sole GT reader. Apply any measurement fixes the plan assigns to this stage. The
> dataset must still validate and the leakage test must still pass before you report `SUCCESS`.

**Deliverable:** `<product>`'s manifest entries + the per-product code/ontology/fixture/infra wiring.
**SUCCESS criteria:** `<product>`'s entries are in the manifest, `dataset.loader.validate(load())`
passes, `tests/test_leakage_guards.py` passes, and `*.status` = `SUCCESS`.

## Stage 3 — Driver per product  (`roles/DRIVER.md`) — loop: grafana, keycloak, netbox

**Task to embed in the prompt (substitute `<product>`):**
> Drive `<product>` through the experiment. Bring up / reuse its infra pinned to the labeled version
> (run the preflight; abort on mismatch), provision its fixture, then run **all of `<product>`'s
> manifest entries** through the four phases end-to-end (prefer cached captures; the orchestrator
> already isolates per-entry failures and continues). Fix any runtime errors and keep going. Score
> with `metrics.py` and record per-entry results. Update the per-product results doc. Process entries
> incrementally; if you approach the context limit, checkpoint into `PROGRESS.md` and report
> `BLOCKED — context` so the orchestrator can relaunch you to resume.

**Deliverable:** `<product>`'s verdicts/captures + a per-product results section (FP on clean,
per-mutation-type detection, navigation success, attribution, cost).
**SUCCESS criteria:** `<product>`'s entries ran/scored (no unhandled crash), results recorded, and
`*.status` = `SUCCESS`. Then gate to the next product's Stage 2.

## Stage 4 — Analyst  (`roles/DRIVER.md`) — run once, after NetBox

**Task to embed in the prompt:**
> Aggregate every product's results into the headline metrics via `metrics.py`: extraction recall,
> FP rate on clean pages, **FN rate per mutation type (M1–M7)**, navigation success, attribution
> accuracy — reported under the plan's **DEV/TEST split** (TEST run once, judgment knobs frozen). Do
> not re-tune anything on TEST. Write the final `RESULTS_full-experiment.md` (per-product +
> cross-product tables, the DEV/TEST split, total cost, and an honest limitations section), and
> refresh `CLAUDE.md`'s status block + any stale docs.

**Deliverable:** `RESULTS_full-experiment.md` + refreshed status docs.
**SUCCESS criteria:** headline metrics computed by `metrics.py` under the DEV/TEST split, results
doc written, and `*.status` = `SUCCESS`.

---

## Feedback classification & control flow

For each finished stage, read `results/_workflow/<STAGE>.status` (authoritative) and the
`<STAGE>.json` envelope, then classify:

- **SUCCESS** — `exit==0`, `is_error==false`, status starts `SUCCESS`. → Record the one-line reason
  + `total_cost_usd`, tick the `PROGRESS.md` box, proceed to the next stage (or next product).
- **BLOCKED — context** (a checkpoint, not a failure) — status starts `BLOCKED` with reason
  `context`. → **Relaunch the same stage** with a prompt appended to resume from `PROGRESS.md`.
  Repeat until it reports `SUCCESS`; if it makes no forward progress across two relaunches, treat as
  a hard stop and report.
- **FAILED** — `exit!=0`, or `is_error==true`, or status starts `FAILED` (or no status written). →
  Relaunch that stage **once**, appending the failure reason + `*.err` tail so it can self-correct.
  If it fails again, **STOP the chain** and report.
- **BLOCKED (other)** — status starts `BLOCKED` with any non-context reason. → **STOP the chain** and
  surface the blocker's one-line reason (do not guess past a genuine blocker — e.g. a missing TEST
  decision, an unbuildable infra dependency, or a proposed invariant violation).

Never start the next stage until the current one is `SUCCESS`. On any hard stop, leave all artifacts
in place for inspection.

---

## Final report (orchestrator output)

After the chain ends (all SUCCESS, or a hard stop), report to the user:

1. **Per stage** (in run order, grouped by product): status, the one-line reason, cost, and
   deliverable path (`PLAN_*.md`, the manifest diff per product, each per-product results section,
   `RESULTS_full-experiment.md`).
2. **Headline metrics** as computed by the Analyst: extraction recall, FP rate (clean), FN rate per
   mutation type, navigation success, attribution accuracy — under the **DEV/TEST split**, with the
   FN-priority framing called out.
3. **Overall outcome and total cost** (sum of `total_cost_usd` across all stages).
4. **If stopped early:** which product/stage, why, the resume point in `PROGRESS.md`, and the exact
   `results/_workflow/<STAGE>.{status,err}` to inspect.
5. Note any working-tree changes are **uncommitted** (commit only if the user asks).

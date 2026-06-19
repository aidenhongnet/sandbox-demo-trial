# PLAN — Ground-truth relabel (doc-vs-deployed-product) + M1 mutation redesign

**Author:** Planner (Stage 1 of `roles/WORKFLOW.md`)
**Date:** 2026-06-18
**Scope:** `grafana-p1-clean` and `grafana-p1-m1` on **OSS Grafana 13.0.2** (the MVP scope; `config.PRODUCT_VERSION`).
**Executor target:** a separate Plan-Executor (Stage 2) applies this verbatim; the Driver (Stage 3) re-runs/re-scores.

> This plan is derived from first-hand evidence: the cached, version-correct (13.0.2 / `grafana-p1-seed-v1`) captures in `results/`, the doc text in the manifest, the verifier's own oracle verdicts, and live re-score smoke tests run during planning. Prior write-ups (`RESULTS_remediation-run.md` "Open items", `RUNBOOK_remediation.md`) were treated as inputs to verify — and they were verified, with one correction (see c17/c18).

---

## 0. Problem restated (derived, not assumed)

Two evaluation-substrate defects, both confined to the two version-pinned grafana-p1 entries:

1. **GT-vs-deployed-product mismatch.** Four clean claims (`c3, c5, c9, c12`) are labeled `is_correct=true` because they were written against the documentation's Cloud/Enterprise/latest assumptions, but the features are genuinely **absent or renamed in OSS 13.0.2**. The verifier returns FALSE on all four — *correctly* — yet they score as false positives. Net effect today (re-score smoke test, oracle verdicts vs current GT): **TP0 / FP6 / FN0 / TN9 / UNC10**; the 6 FPs are `c2, c3, c5, c9, c12, c17`.

2. **Invalid navigation mutation (M1).** The current M1 changes doc step 1 from "Click **Dashboards**" → "Click **Home**". On 13.0.2 the global "New" button on the Home page still creates a dashboard, so the documented path reaches the intended end state and `c1 → TRUE (3/3)` — **M1 is not an observable contradiction** and never exercises nav-path detection (confirmed by the Pass B replay `grafana-p1-m1__home.replay.json`).

### What is NOT wrong (do not "fix" these)
- **c2** ("Add new element icon is a blue plus sign") — the icon is a *white* plus on a *blue* button; the verifier's FALSE is a genuine (defensible) color-nuance error, the **one true FP**. Leave `is_correct=true`. Keeps the verifier honest.
- **c17 / c18** (Repeat direction / Max per row) — **fixture-coverage gap, NOT a product difference.** The doc itself (clean content **line 201**: *"06. For panels in a **custom layout**, set the following options:"*) scopes these controls to **Custom-grid** panels. The seed fixture uses **Auto grid**, so the cached capture correctly shows them absent. Leave `is_correct=true`; record as a fixture-coverage limitation (see §7, optional follow-up). The prior analysis's "c17 fixture-state gap" call is upheld.
- The **other 100 manifest entries** (all `product_version=None`, un-migrated) and the **other grafana-p1 mutations** (`m2–m6`) are out of scope — do not touch.

---

## 1. Relabels to apply (issue #1) — exact, with provenance

Apply to **both** `grafana-p1-clean` **and** `grafana-p1-m1` (same doc, same deployed product). Flip `is_correct: true → false` and attach a per-claim `provenance` string (new field, §3).

| claim_id | type | old `is_correct` | new `is_correct` | oracle verdict | becomes | provenance (deployed-product evidence) |
|---|---|---|---|---|---|---|
| `grafana-p1-c3` | ui_element | true | **false** | FALSE 3/3 | FP→**TP** | Edition gap |
| `grafana-p1-c5` | behavior | true | **false** | FALSE 2/3 | FP→**TP** | Edition gap |
| `grafana-p1-c9` | ui_element | true | **false** | FALSE 3/3 | FP→**TP** | Edition gap |
| `grafana-p1-c12` | field_value | true | **false** | FALSE 2/3 | FP→**TP** | Version/label drift |

**Exact `provenance` strings** (set verbatim on the matching claim in both entries):

- **c3:** `"OSS Grafana 13.0.2: the new-panel dialog presents only 'Configure visualization' and 'Use library panel' — 'Use saved query' is absent (Enterprise/Cloud-only). Evidence: results/descriptions/13.0.2/grafana-p1-seed-v1/new-panel-options.txt ('Use saved query is NOT present'). Relabeled 2026-06-18 from live 13.0.2 capture."`
- **c5:** `"OSS Grafana 13.0.2: the 'savedQueries' feature toggle is disabled, so 'Use saved query' and the 'Saved queries' drawer do not exist (Enterprise/Cloud public-preview only). Evidence: results/descriptions/13.0.2/grafana-p1-seed-v1/saved-queries-drawer.txt + /api/frontend/settings featureToggles (no 'savedQueries'). Relabeled 2026-06-18 from live 13.0.2 capture."`
- **c9:** `"OSS Grafana 13.0.2: the dashboard edit toolbar has 7 items; 'Filters overview' and 'Dashboard insights' are absent (not present in OSS). Evidence: results/descriptions/13.0.2/grafana-p1-seed-v1/dashboard-edit-mode-toolbar.txt ('Filters overview: NOT PRESENT', 'Dashboard insights: NOT PRESENT'). Relabeled 2026-06-18 from live 13.0.2 capture."`
- **c12:** `"Grafana 13.0.2: the layout option is labeled 'Custom grid' (in both the inline Options panel and Settings -> Default grid), not 'Custom' as the doc states — version/label drift. Evidence: results/descriptions/13.0.2/grafana-p1-seed-v1/dashboard-settings-layout.txt ('the option is labeled \"Custom grid\", not \"Custom\"'). Relabeled 2026-06-18 from live 13.0.2 capture."`

**Also update the entry-level provenance** on both entries:
- `labeled_by`: `"human doc-review (Grafana /latest docs, v13.0 family); live re-validated on OSS 13.0.2 2026-06-18 (per-claim provenance on relabeled claims c3/c5/c9/c12)"`
- `labeled_against_version`: keep `"13.0.2"`.

> Provenance is recorded in **three** places: per-claim `provenance` field (machine-readable, co-located with the label), entry-level `labeled_by`, and a human-readable "Relabel provenance" table in `RESULTS_remediation-run.md` (§6).

---

## 2. M1 mutation redesign (issue #2) — exact

**New mutation:** change doc **step 2's menu selection** from **"New Dashboard"** to **"Import dashboard"**, and **revert step 1** back to "Dashboards" (the old Home change is dropped). Both items exist in the global "New" menu (confirmed by the replay: New → {New dashboard, Import dashboard, New alert rule}), but **"Import dashboard" opens the dashboard-import screen (`/dashboard/import`), not a new empty dashboard.** Unlike the Home-vs-Dashboards swap, the global "New" button **cannot** tolerate this — the wrong menu item lands on the wrong screen regardless of entry point. This is a genuine, **observable** wrong-navigation-path contradiction.

### 2a. Doc content (`content` field of `grafana-p1-m1`)
Regenerate from the **clean** content with exactly one line changed (clean line 14 must read "Dashboards"; only line 15 changes). Verified: m1 currently differs from clean only at line 14.

- **Line 14 (revert to clean):** `01. Click **Dashboards** in the main menu.`
- **Line 15 (mutate):** `02. Click **New** and select **New Dashboard**.` → `02. Click **New** and select **Import dashboard**.`

Deterministic transform (executor): `m1_content = clean_content.replace("02. Click **New** and select **New Dashboard**.", "02. Click **New** and select **Import dashboard**.")`. Assert the result differs from clean at exactly line 15 and equals clean at line 14.

### 2b. `mutation` object (`grafana-p1-m1`)
```json
{
  "type": "M1",
  "name": "wrong_nav_path_import_instead_of_new_dashboard",
  "description": "Changed the second navigation step's menu selection from 'New Dashboard' to 'Import dashboard'. Both items exist in Grafana 13.0.2's global 'New' menu, but 'Import dashboard' opens the dashboard-import screen (/dashboard/import), not a new empty dashboard, so the documented path no longer reaches the asserted end state. Replaces the prior 'Home instead of Dashboards' mutation, which was not an observable contradiction in 13.0.2 (the global 'New' button reaches a new dashboard from Home too).",
  "original_text": "02. Click **New** and select **New Dashboard**.",
  "mutated_text": "02. Click **New** and select **Import dashboard**.",
  "location": { "line_start": 15, "line_end": 15 },
  "affected_claim_ids": ["grafana-p1-c1"]
}
```

### 2c. GT `c1` claim (`grafana-p1-m1` only)
Make the GT claim faithfully reflect the mutated doc (it currently still says "New Dashboard"):
- `text`: `"Clicking 'Dashboards' in the main menu and then clicking 'New' > 'Import dashboard' opens a new empty dashboard."`
- `type`: `nav_path` (unchanged) · `target_screen`: `New Dashboard` (unchanged — the *claimed* destination) · `line_number`: `14` (unchanged) · `is_correct`: **false** (unchanged — it is the mutation finding).
- `expected_findings` stays `["grafana-p1-c1"]`.

**Expected verifier verdict after re-run:** `c1 → FALSE`, `mutation_detected = True`. The Pass B replay walks Dashboards → New → Import dashboard and records `resulting_url=/dashboard/import` (not `/dashboard/new`); the verifier's `nav` atom for "opens a new empty dashboard" is judged against the trace → FALSE → claim FALSE. (`grafana-p1-clean` c1 stays TRUE — the clean path is unchanged.)

**Fallback** (only if the Driver finds "Import dashboard" ambiguous on live 13.0.2): instead mutate to a non-existent menu item — `02. Click **New** and select **Blank dashboard**.` — so the replay records `control_present=false` for that step. Keep all other fields analogous. Prefer the Import-dashboard design (a real control reaching a real-but-wrong screen is a more authentic "wrong path").

---

## 3. Schema / support changes (keep leakage guards intact)

The current validator hard-codes "clean ⇒ all claims correct" and "mutated ⇒ false claims == expected_findings", which is **incompatible with the mission's premise** (real docs drift from the product even when un-mutated). Two minimal, leakage-safe changes — both in files **not** governed by the L1 prediction-module guard (`dataset/schema.py`, `dataset/loader.py`; the FORBIDDEN scan in `tests/test_leakage_guards.py` covers only `extract/plan/drive/verify`).

### 3a. `dataset/schema.py` — add per-claim provenance
In `class Claim(TypedDict)` add (after `line_number`):
```python
    # Label provenance (L6): for a claim whose is_correct=False reflects a real
    # doc-vs-deployed-product discrepancy (not an injected mutation), the concrete
    # evidence. Read only by loader.validate + metrics.py; never by prediction modules.
    provenance: NotRequired[str]
```

### 3b. `dataset/loader.py` — relax the is_correct/is_mutated coupling, enforce provenance
Replace the whole `if e.get("is_mutated"): … else: …` block (currently the block that ends with the `"clean entry has incorrect claims"` error) with:

```python
        # is_correct is INDEPENDENT of is_mutated: a claim may be is_correct=false
        # on a CLEAN doc when the real documentation drifts from the deployed
        # product (the mission's premise). Any false claim that is NOT a mutation
        # finding is a "natural discrepancy" and must carry per-claim provenance (L6).
        incorrect = {c["id"] for c in claims if not c.get("is_correct")}
        expected_set = set(e.get("expected_findings", []))

        if e.get("is_mutated"):
            mut = e.get("mutation")
            if not mut:
                errors.append(f"{eid}: is_mutated=true but mutation is null")
            else:
                if mut.get("type") not in VALID_MUTATION_TYPES:
                    errors.append(f"{eid}: invalid mutation type '{mut.get('type')}'")
                if not mut.get("original_text"):
                    errors.append(f"{eid}: mutation missing original_text")
                if not mut.get("mutated_text"):
                    errors.append(f"{eid}: mutation missing mutated_text")
                if mut.get("original_text") == mut.get("mutated_text"):
                    errors.append(f"{eid}: mutation original_text == mutated_text")
                affected = set(mut.get("affected_claim_ids", []))
                if affected != expected_set:
                    errors.append(
                        f"{eid}: affected_claim_ids {affected} != expected_findings {expected_set}"
                    )
            # Every expected finding must be labeled is_correct=false; additional
            # false claims (natural discrepancies) are allowed beyond them.
            missing = expected_set - incorrect
            if missing:
                errors.append(f"{eid}: expected_findings {missing} not marked is_correct=false")
        else:
            if e.get("mutation") is not None:
                errors.append(f"{eid}: is_mutated=false but mutation is not null")
            if e.get("expected_findings"):
                errors.append(f"{eid}: clean entry has non-empty expected_findings")

        # Provenance discipline (L6): a false claim that is not a mutation finding
        # is a natural doc-vs-product discrepancy and must be justified.
        natural_false = incorrect - expected_set
        prov = {c["id"]: c.get("provenance") for c in claims}
        for cid in sorted(natural_false):
            if not prov.get(cid):
                errors.append(
                    f"{eid}: claim {cid} is_correct=false (natural discrepancy) but has no provenance (L6)"
                )
```

**Verified against all cases** (logic checked during planning): the 100 un-migrated entries and `m2–m6` stay valid (their `incorrect == expected_set`, so `missing`/`natural_false` are empty); `grafana-p1-clean` post-relabel needs provenance on c3/c5/c9/c12 (supplied); `grafana-p1-m1` post-relabel has `incorrect={c1,c3,c5,c9,c12}`, `expected_set={c1}` → `missing={}`, `affected==expected`, natural_false={c3,c5,c9,c12} need provenance (supplied).

> **No change** to `metrics.py` (still the sole GT reader; `score_verdicts` already handles `is_correct=False` per claim), to the prediction modules, or to the orchestrator. The leakage test is unaffected.

---

## 4. Editing the manifest safely

`dataset/manifest.jsonl` is 102 single-line JSON entries, **1.2 MB, serialized with `ensure_ascii=False`** (raw UTF-8, no `\uXXXX`). Edit **only** the two target lines; leave the other 100 byte-for-byte unchanged. Recommended approach (Python):

1. Read all lines. For each line, parse just enough to read `"id"`.
2. For `grafana-p1-clean`: set `is_correct=false` + `provenance=<§1 string>` on c3/c5/c9/c12; update `labeled_by`. (No content/mutation change.)
3. For `grafana-p1-m1`: same four relabels + provenance + `labeled_by`; **plus** the §2 redesign — regenerate `content`, replace the `mutation` object, and rewrite `c1`'s `text`.
4. Re-serialize **only** the two edited entries with `json.dumps(entry, ensure_ascii=False)`; write all lines back (target lines replaced, others verbatim), preserving the trailing newline.

---

## 5. Re-score vs re-run — explicit

| Dataset | Action | Why | Infra |
|---|---|---|---|
| `grafana-p1-clean` | **RE-SCORE ONLY** | Predictions (verdicts) are unchanged; only the GT changed. | none |
| `grafana-p1-m1` | **RE-RUN** (Pass B replay + verify) | The documented path changed → the replay trace must be regenerated against the live product, then c1 re-verified. Pass A captures are cached/reused. | Grafana 13.0.2 + Chrome CDP |

### 5a. Re-score `grafana-p1-clean` (no infra)
```bash
python -c "from pipeline import metrics; import json; v={x['claim_id']:x['result'] for x in json.load(open('results/verdicts/grafana-p1-clean.oracle.json',encoding='utf-8'))}; print(metrics.format_verification(metrics.score_verdicts(v,'grafana-p1-clean')))"
```
**Expected (validated by smoke test during planning):** `TP 4 · FP 2 · FN 0 · TN 9 · UNC 10` · precision 0.667 · recall 1.000 · coverage 60%. Remaining FPs: `c2` (color nuance) and `c17` (fixture-coverage gap). `results/verdicts/grafana-p1-clean.json` holds identical verdicts and re-scores the same.

### 5b. Re-run `grafana-p1-m1` (infra up)
1. Ensure Grafana **13.0.2** + Chrome CDP are running and the seed fixture is provisioned (e.g. `python -m pipeline.drive grafana-p1-clean --setup`; Pass A is cached so this is mostly cache hits + the version preflight). Confirm `Version preflight OK: deployed Grafana 13.0.2`.
2. Delete the now-stale replay so it is regenerated:
   `results/traces/13.0.2/grafana-p1-seed-v1/grafana-p1-m1__home.replay.json` and `…__home.replay.authored.json`.
3. Re-run m1 via the **oracle path** (GT-aligned IDs → a fully interpretable confusion matrix; the seeded c1 text now carries the redesigned mutation):
   ```bash
   python -c "from pipeline import orchestrator; orchestrator.run_pipeline('grafana-p1-m1', oracle_claims=True)"
   ```
   This reuses cached Pass A captures, drives the **new** Pass B replay `grafana-p1-m1__new-dashboard.replay.json` (c1's `target_screen='New Dashboard'` → slug `new-dashboard`), and re-verifies.
4. Score:
   ```bash
   python -c "from pipeline import metrics; print(metrics.format_verification(metrics.score_verdicts(metrics.load_verdict_results('grafana-p1-m1'),'grafana-p1-m1')))"
   ```
   **Expected:** `c1 → FALSE`; `mutation_detected = True`; matrix `TP 5 · FP 2 · FN 0 · TN 8 · UNC 10` (c1 joins c3/c5/c9/c12 as TP; c2/c17 remain FP). Confirm the new replay shows the documented Import-dashboard step landing on `/dashboard/import` (not `/dashboard/new`).

   > **Actual (Stage-3 Driver, 2026-06-18).** Binding criteria met exactly: `c1 → FALSE`
   > (3/3, conf 1.0), `mutation_detected = True`, replay `final_url=/dashboard/import`,
   > **FN = 0**. Full matrix came in at **`TP 5 · FP 4 · FN 0 · TN 9 · UNC 7`** — the
   > FP/TN/UNC split is noisier than predicted because the N=3 self-consistency verifier is
   > stochastic: this run c18 + c25 resolved FALSE (2/3 each) instead of abstaining (c18 is
   > the *same* fixture-coverage gap as c17, a defensible detection; c25 is run noise), and
   > one normally-uncertain claim resolved TRUE (TN 9 vs 8). No design change — the
   > Import-dashboard mutation worked as intended; the fallback (§2c) was not needed. Live
   > nuance: the menu item is labeled just "Import" (no "dashboard" suffix) but still routes
   > to `/dashboard/import`, so the contradiction holds.
5. (Optional) refresh `results/pipeline_report*.json` if a full `python -m pipeline.orchestrator --oracle-claims` is run; clean Pass A cache makes this cheap.

> If stream-json / live driving is unavailable, the agent-authored replay fallback still applies (`drive._build_trace`). The mutation's contradiction is in the *destination URL*, which the replay records either way.

---

## 6. Documentation to update

1. **`RESULTS_remediation-run.md`** (primary):
   - Headline + "Clean verifier analysis — the '6 FP' decomposed": replace with the post-relabel matrix **TP4/FP2/FN0/TN9/UNC10**; reclassify c3/c5/c9/c12 rows as **TP (GT corrected, provenance recorded)**; keep c2 (genuine error) and c17 (fixture-coverage gap) as the 2 remaining FPs.
   - "The doc-vs-OSS-edition gap" section: change status from *needs a decision* → **RESOLVED via option (a): relabeled c3/c5/c9/c12 `is_correct=false` with per-claim provenance.** Add a **"Relabel provenance"** table (claim · old→new · evidence file).
   - "M1 … the mechanism works; the mutation does not contradict 13.0.2" section: replace with the **redesign** ("New > Import dashboard" → `/dashboard/import`), the new replay artifact name, and the re-run result (`c1→FALSE`, `mutation_detected=True`).
   - Acceptance scorecard: row **#2 Oracle valid → ✅** (ex-FP flips done); row **#3 M1 detected → ✅** (redesigned + detected).
   - Add a one-line note: c17/c18 are a **fixture-coverage gap** (doc scopes Repeat direction to Custom layout; fixture uses Auto grid) — not relabeled; see §7.
2. **`CLAUDE.md`** → "Current status" + "Open items":
   - Open item **#1 (doc-vs-OSS gap): RESOLVED** — relabeled c3/c5/c9/c12 with provenance; clean matrix TP4/FP2/FN0/TN9/UNC10.
   - Open item **#2 (M1 not a real contradiction): RESOLVED** — redesigned to "New > Import dashboard"; c1→FALSE; mutation_detected=True.
   - Note the schema/validator change: clean entries may carry provenance-backed `is_correct=false`; mutated entries may have natural discrepancies beyond `expected_findings`.
   - Items #3 (recall matcher) and #4 (E2E ID alignment caveat) stay open (out of scope).
3. **`RUNBOOK_remediation.md`**: update acceptance checks **#2** and **#3** to "resolved" with the new expectations; annotate the Step-0 re-score note (the post-relabel oracle matrix is TP4/FP2/FN0/TN9/UNC10; the historical "TN6/FP10/UNC9" was a pre-relabel instrumentation-correctness datapoint).
4. **`RESULTS_mvp-run.md`** (historical): minimal — add a single forward-pointer line noting the doc-vs-OSS gap and M1 were later resolved (see `RESULTS_remediation-run.md`). Do not rewrite history.
5. **Manifest** itself carries the per-claim `provenance` + updated `labeled_by` (the authoritative machine-readable record).

---

## 7. Validation / acceptance checklist (Executor + Driver)

Executor (Stage 2), after edits — both must pass:
```bash
python tests/test_leakage_guards.py
python -c "from dataset import loader; print(loader.validate(loader.load()) or 'manifest OK')"
```
Expect `L1 leakage guards: OK` and `manifest OK`. Then run the **clean re-score** (§5a) and confirm TP4/FP2/FN0/TN9/UNC10.

Driver (Stage 3): bring up infra, run the **m1 re-run** (§5b), confirm `c1→FALSE` + `mutation_detected=True` + replay lands on `/dashboard/import`, then refresh the docs in §6 with the actual numbers.

**Definition of done:**
- Manifest validates; leakage test passes.
- `grafana-p1-clean` re-scores to TP4/FP2/FN0/TN9/UNC10 (0 FN preserved).
- `grafana-p1-m1` re-runs to `c1→FALSE`, `mutation_detected=True`.
- Provenance recorded per-claim + entry-level + in `RESULTS_remediation-run.md`.
- All four docs in §6 updated; no un-scoped files changed.

---

## 8. Optional follow-up (note, do not block on)

- **Fixture coverage for c17/c18 (Repeat direction / Max per row).** These need a panel under a **Custom-grid** layout to be observable. A future fixture revision could add one Custom-grid panel with a repeat variable, then **bump `config.FIXTURE_ID`** (so stale Auto-grid captures aren't reused) and re-verify c17/c18. Until then they remain a documented fixture-coverage gap (the 2nd remaining FP), not a relabel.
- Open items #3 (semantic recall matcher) and #4 (E2E ID alignment) are unchanged and out of this plan's scope.

---

## 9. Leakage-guard compliance (explicit)

- Only `metrics.py` reads `is_correct` / `expected_findings` / `mutation` at prediction time. **Unchanged.**
- `loader.py` and `schema.py` are validation/typing modules, **not** in `tests/test_leakage_guards.py`'s `PREDICTION_MODULES`; reading GT there is allowed and pre-existing.
- The new `provenance` field is read only by `loader.validate`; prediction modules read `entry["content"]` and their own extracted claims, never the GT claim objects.
- No prediction module, nor the orchestrator, is modified. `tests/test_leakage_guards.py` must still pass unchanged (acceptance gate).

WORKFLOW_STATUS: SUCCESS — plan written to PLAN_gt-relabel-and-m1-redesign.md (relabel c3/c5/c9/c12 with provenance + validator relaxation; redesign M1 to 'New > Import dashboard'; clean re-score, m1 re-run, docs refresh).

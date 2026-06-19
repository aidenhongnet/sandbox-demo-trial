# RESULTS — Stage 02-grafana-build (pipeline generalization + grafana dataset audit)

**Role:** Plan-Executor (Builder) · **Stage:** `02-grafana-build` · **Date:** 2026-06-18
**Governing plan:** `PLAN_full-experiment.md` (§2 generalization, §4 measurement, §1 audit).
Grafana is the TEMPLATE product, so this stage also performs the one-time pipeline
generalization that Keycloak/NetBox reuse.

---

## 1. Headline

- **Pipeline generalized to product-parametric** using the Grafana code as template:
  a `PRODUCTS`/`ProductSpec` registry in `config.py`; a `product` argument threaded
  through extract/plan/drive/verify/orchestrator; per-product ontology loading; the
  plan dependency graph now **derived from the ontology `parent` field** (the hardcoded
  `GRAFANA_P1_DEPS` is deleted); captures namespaced by `<product>/<version>/<fixture>/`.
  Grafana behavior is **identical** (deps map byte-equal to the old one; cached p1
  captures migrated and still resolve; oracle re-score unchanged).
- **Measurement fix shipped (one matcher, used twice):** a semantic LLM-judge claim
  matcher in `metrics.py` (the sole GT reader) fixes open item #3 (extraction recall)
  and open item #4 (E2E verdict→GT id alignment). **Calibration HARD GATE met:
  extraction recall 1.000 on grafana-p1-clean** (was 0.04 with word-overlap).
- **Leakage guard L1 intact** (pytest 4/4), **manifest validates** (0 errors) after all edits.

---

## 2. Pipeline generalization (plan §2.1 surface)

| File | Change | Grafana-identical? |
|---|---|---|
| `config.py` | Added frozen `ProductSpec` dataclass + `PRODUCTS` registry (grafana/keycloak/netbox, pinned per §3) + `spec()`. Kept every `GRAFANA_*`/`PRODUCT_VERSION`/`FIXTURE_ID` as a thin alias of `PRODUCTS["grafana"]`. `capture_subdir(base, product, …)` now namespaces `base/<product>/<version>/<fixture>/`; version/fixture default from the spec (config, never the manifest). | yes (aliases) |
| `ontology.py` | `normalize(screen, product, …)` + `_screens(product)` (lru-cached per product) load `fixtures/<product>/screen_ontology.json`. Added `deps(product)` deriving the nav graph from each screen's `parent`. | yes |
| `extract.py` | `ontology.normalize(c.target_screen, product)` — one-line thread-through. | yes |
| `plan.py` | **Deleted `GRAFANA_P1_DEPS`**; `run(dataset_id, product)` uses `ontology.deps(product)`; `_build_product_context(product)` pulls name/url/creds from the spec. | deps map byte-equal |
| `drive.py` | Per-product infra adapter selected by `product`: `start_product` (docker run / compose), `wait_for_product`, `get_product_version` (dispatch: grafana `/api/health`, netbox `/api/status/`, keycloak token+`/admin/serverinfo` w/ image-tag fallback), `assert_version(product)`, `pre_auth(product)`, `provision_fixture(product)`, `run(dataset_id, product)`. Captures/traces keyed by product. Grafana-named thin aliases kept. **No forbidden token; no `mutation` word.** | yes |
| `verify.py` | `run(dataset_id, product)` + `_load_screen_states(dataset_id, product)` (product-namespaced captures). | yes |
| `orchestrator.py` | Threads `product` into plan/drive/verify; `--product`/`--dataset` selection via `loader.filter_by` (prediction inputs only); passes the §4 alignment into `score_verdicts` for non-oracle runs. | default run unchanged |

L1 standing constraint upheld: `metrics.py` stays the sole GT reader; the prediction
modules contain none of `is_correct`/`expected_findings`/`_load_ground_truth`/`MANIFEST_PATH`/`mutation`.

Keycloak/NetBox specs are pre-pinned in the registry, and the drive adapter dispatches on
`bring_up`/`version_probe`, so their Stage-2 enablement is mechanical (spec values + ontology
crawl + fixture + compose file). NetBox `compose_file` and per-product `fixture_setup_<product>.txt`
are referenced but supplied in their own stages.

## 3. Measurement fix — semantic claim matcher (plan §4)

`metrics.semantic_match(extracted, gt_claims)` → gt_id→ext_id. Two-stage, L1-clean:
word-overlap auto-accept (≥0.45) then a chunked (5/call) LLM judge that matches **by
meaning, generously** (a candidate covering a *constituent part* of a compound GT claim
counts — the extractor atomizes one fact into several claims). Cached per
`(dataset_id, content-signature)` in-process + on disk (`results/_match_cache/`). Used by
`score_extraction` (#3) and `alignment_for`→`score_verdicts(alignment=)` (#4); unmatched
extracted verdicts become extraction FPs (not verification FPs), unmatched GT becomes a
coverage gap (not an FN). See `results/_workflow/matcher-calibration.md`.

**Calibration (HARD GATE) — grafana-p1-clean, real 111-claim extraction:**

| matcher | recall | matched/GT |
|---|---|---|
| word-overlap (old) | 0.040 | 1/25 |
| **semantic (sonnet, chunk 5 + floor)** | **1.000** | **25/25** |

`config.MODEL_MATCH="sonnet"` was set during this DEV calibration (Haiku was unreliable on
dense claim clusters: 0.6–0.8 recall, high variance). Judgment-bearing knob → frozen before NetBox.

---

## 4. Grafana dataset audit / relabel (plan §1.2)

<!-- FILLED AFTER LIVE UI AUDIT + defaults.ini -->

### 4a. Version pins
All 34 grafana entries carry `product_version`/`labeled_against_version`/`labeled_by` = `13.0.2`.

### 4b. Mutation-object normalization
**None needed for grafana** — all 29 grafana mutation objects are schema-clean (every one has
`name`, `location` as `{line_start,line_end}`, full canonical key set, `affected_claim_ids ==
expected_findings`). The §0.4 `name`-omission / `label` / free-text-`location` issues are
entirely on keycloak + netbox (verified across all 87 mutation objects).

### 4c. p3 (config-file reference) — clean claims accurate vs the pinned image
Audited all 16 default/enum claims of `grafana-p3-clean` against the running container's
`/usr/share/grafana/conf/defaults.ini` (`grafana/grafana:13.0.2`): http_port=3000,
evaluation_timeout=30s, max_attempts=3, versions_to_keep=20, org_user=10, min_refresh_interval=5s,
default_language=en-US, cookie_samesite=lax, type=sqlite3, … **all match the doc → no p3 clean
relabels.** p3 is a config-file page (no UI surface); under a UI-only verifier most p3 claims
legitimately resolve UNCERTAIN (plan §1.2 reference-page caveat) — honest, not an FN.

### 4d. Live-UI clean relabels (p2/p4/p5) — evidence from a live OSS 13.0.2 audit
Confirmed against the running build (`results/_workflow/grafana-ui-audit-findings.md`). Six
clean claims relabeled `is_correct=true→false`, each with a per-claim `provenance` (L6) citing the
concrete UI observation; the relabel propagates to every entry of that page (provenance on the
natural-drift copies, skipped where the claim is that entry's mutation finding). 45 provenance-backed
drift-claim instances result across the 34 grafana entries.

| claim | old→new | OSS 13.0.2 evidence (relabel reason) |
|---|---|---|
| `grafana-p2-c1` | T→**F** | Left nav has **"Alerting"** as a top-level item; **no "Alerts & IRM"** parent (that is Cloud nav). The doc's "Alerts & IRM > Alerting" path doesn't exist. |
| `grafana-p2-c19` | T→**F** | Integration dropdown lists **22** types; **"Line" is absent** (0 results). The doc's 23-item list names Line. |
| `grafana-p4-c12` | T→**F** | Color scheme is a **flat list of 20**; the doc's umbrella schemes "Single/Multiple continuous colors (by value)" **don't exist** as options (5 Viridis-family schemes are extra/undocumented). |
| `grafana-p4-c13` | T→**F** | No "Single continuous color (by value)" scheme; Blues/Reds/Greens/Purples exist only as flat top-level "(by value)" schemes, not under that umbrella. |
| `grafana-p4-c14` | T→**F** | No "Multiple continuous colors (by value)" scheme; the 6 palettes exist only flat, not under that umbrella. |
| `grafana-p5-c10` | T→**F** | Notification policies root is labeled **"Default policy"**, not "Default notification policy". |

**Kept TRUE (auditor over-grouping corrected):** `grafana-p5-c7` — its named destinations (email,
Slack, Grafana IRM [webhook shim], PagerDuty, webhooks) **all exist** in OSS; the "Line" gap is
specific to p2-c19's full enumeration, not p5-c7's example list. `grafana-p2-c3` (Choose Alertmanager
dropdown) → **UNCERTAIN, not relabeled**: the selector only renders when an external Alertmanager is
configured (a seed-state/fixture-coverage gap, like p1-c17), so the doc isn't wrong.

### 4e. Mutation observability audit + redesigns (plan §1.2.3 / §0.3)
All 29 grafana mutations were checked for an observable contradiction in the deployed UI.

**Redesigned (recorded, mirror `PLAN_gt-relabel-and-m1-redesign.md`):**
- **`grafana-p2-m1`** (M1) — re-anchored. Its clean nav baseline ("Alerts & IRM") is itself drift
  (p2-c1 relabel), so the old mutation tested nothing. Now: real OSS path **Alerting →
  Notification configuration**, mutated to a wrong second step **"Alert rules"** → lands on
  `/alerting/list`, not Contact points. c1 text + `target_screen` ("Alert rules list") updated; an
  isolated, observable wrong-nav contradiction.
- **`grafana-p3-m5`** (M5, §0.3-named) — anchored to observable runtime state. c1's `target_screen`
  is now **"Server admin settings"** (`/admin/settings` renders the effective `server.http_port=3000`;
  the instance also binds 3000), so the mutated "default 8080" is a detectable contradiction instead
  of an unobservable config-file default. Mutation text unchanged (3000→8080).
- **`grafana-p4-m6`** (M6, §0.3-named) — reframed from a brittle exact-value example
  ("140W vs 0.00014MW", which needs a deterministic data-value fixture) to an **observable behavior**:
  Grafana auto-scales a unit by magnitude (visible in the panel editor with live data); the mutation
  now asserts the opposite ("does not scale"). c20 text + content + mutation object updated.

**Confirmed observable as drafted (kept):** p2-m3 (+New vs +Create), p2-m4 (Integration vs
Integration type), p2-m7 (Contact points vs notification channel heading), p4-m1 (Misc vs Format),
p4-m3 (Standard options vs Standard field options), p4-m4 (Decimals vs Decimal places), p4-m5
(No-value default "-" vs empty — audit confirmed the hyphen), p5-m3 (Grafana IRM vs IRP), p5-m4
(Default vs Root policy name), p5-m6 (label vs annotation matching), p5-m7 (Contact points vs
Notification channels). p4-m2 (transformation step order) and p2-m2 (contact-point step order) are
observable to an agent that drives the multi-step flow; p5-m1 lands on the rule editor's
contact-point/policy choice.

**Documented limitations (honest, NOT fabricated — plan §1.2 reference/descriptive caveat):**
- **`grafana-p3-m1`** (config file path `/etc/grafana/grafana.ini`) and **`grafana-p3-m6`** (env-var
  vs file precedence) are **text/knowledge-only by nature** — a config-file page has no UI surface for
  these; the verifier will legitimately **abstain (UNCERTAIN)**, which is a contradiction-abstention,
  not a missed contradiction (FN). p3-m3/m4/m7 are weakly observable via `/admin/settings` (key names /
  effective values).
- **`grafana-p5-m5`** (default notification-message contents) requires firing an alert and inspecting
  the delivered message — not observable without a notification-delivery fixture; UNCERTAIN is honest.
- p3 is a config-file reference page overall: most of its claims resolve UNCERTAIN under a UI-only
  verifier (its 16 default/enum claims were audited TRUE against the image's `defaults.ini`).

**Ontology extension (L5):** `fixtures/grafana/screen_ontology.json` extended from 23 (p1-only) to 36
screens, adding the p2-p5 areas (Alerting/Notification configuration/Contact points/Integration
dropdown/Templates/testing dialog; Notification policies/Alert rules list/Alert rule editor; Server
admin settings; panel-editor Unit + Color scheme dropdowns) — derived from the claim-blind live-UI
audit, not the manifest. All parents resolve, no cycles; p1 deps unchanged. The Driver should
verify/extend these via a fuller crawl before driving p2-p5.

---

## 5. Gates (run, pasted in the final status message)
- `python -m pytest tests/test_leakage_guards.py` → **4 passed**.
- `loader.validate(load())` → **0 errors**.
- matcher calibration on grafana-p1-clean → **recall 1.000** (gate ~0.9).

## 6. Limitations / open items
- Extraction open #3 RESOLVED (semantic matcher, recall 0.04→1.0). Open #4 RESOLVED
  (alignment threaded into `score_verdicts`); E2E confusion matrices are now trustworthy.
- **Driver follow-ups (Stage 03-grafana-drive):** (a) the p2-p5 ontology screens are an
  audit-derived starting map — verify/extend via a fuller claim-blind crawl; (b) provision
  p2-p5 fixtures (a seed contact point / notification policy / panel so the screens are
  reachable) and reach `/admin/settings` for p3-m5; (c) p3-m1/m6 and p5-m5 are expected to
  resolve UNCERTAIN (record the abstention rate per page type — honest, not FN).
- The matcher (sonnet, prompt+thresholds) is a judgment-bearing knob → must be **frozen**
  before NetBox (plan §4.2 `FROZEN_KNOBS.md`).

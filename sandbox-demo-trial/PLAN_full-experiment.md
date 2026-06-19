# PLAN — Full Experiment (scale the verification pipeline to 3 products)

**Role:** Planner (`roles/PLANNER.md`) · **Stage:** `01-plan` · **Date:** 2026-06-18
**Consumers:** the Stage-2 Builders (`PLAN-EXECUTOR`) and Stage-3 Drivers (`DRIVER`) per
`roles/WORKFLOW.md`. Read this first, then your stage section.

This plan scales the validated Grafana-`p1` pipeline to the full experiment in
`MISSION.md` + `dataset-plan.md`: **3 products × 5 pages, the M1–M7 matrix (87
mutations, 102 entries total)**, run end-to-end on correctly-pinned infra, scored by
`metrics.py` under a real DEV/TEST split with per-mutation-type FN rates.

---

## 0. What I verified (evidence, not assumptions)

I treated every prior write-up as input to verify. The live state differs materially
from WORKFLOW.md's "current state" — these findings reshape the work:

1. **The dataset is already fully drafted, and it is good.** `dataset/manifest.jsonl`
   holds **all 102 entries** (15 clean + 87 mutations). The per-page mutation matrix
   **exactly** matches `dataset-plan.md` (per product: M1×5, M2×3, M3×5, M4×5, M5×4,
   M6×4, M7×3). `dataset.loader.validate(load())` returns **0 errors** and
   `tests/test_leakage_guards.py` **passes** (verified this session). Claims are real,
   typed, screen-attributed prose — not placeholders.
   - **Therefore WORKFLOW.md's "14 of 15 pages unlabeled; matrix unbuilt" is STALE.**
2. **…but only Grafana-`p1` is labeled against the *deployed* build.** Only **2/102**
   entries carry `product_version`/`labeled_against_version`/`labeled_by`
   (grafana-p1-clean, grafana-p1-m1); only **8 claims** carry `provenance`. The other
   100 entries are an *unvalidated draft*: every clean page except grafana-p1 is labeled
   "all claims true" (no doc-vs-product drift found yet because none was looked for), and
   no mutation outside grafana-p1-m1 has been confirmed **observable** in the deployed UI.
   - **Therefore the Builder's real job is AUDIT + RELABEL + VALIDATE the draft against
     the deployed build, plus pipeline generalization — NOT authoring from scratch.**
3. **Mutation quality is high but a minority are borderline-observable.** Sampled
   mutations are well-crafted (e.g. keycloak-p1-m3 `Create`→`Save` button; netbox-p2-m2
   step-order swap; netbox-p5-m7 `Prefix`→`Subnet` terminology). But some encode
   contradictions that are hard or impossible to observe through the UI as deployed:
   grafana-p3-m5 (`http_port` default in `grafana.ini`), keycloak-p3-m4 (pbkdf2 default
   "for FIPS deployments"), grafana-p4-m6 (unit auto-scaling `140W` vs `0.00014MW`).
   These need the **M1-redesign treatment** (see `PLAN_gt-relabel-and-m1-redesign.md`):
   make the contradiction observable in the deployed product, or the entry tests nothing.
4. **Mutation-schema drift in the draft.** 28/87 mutation objects omit `name` (some use
   `label`/`detail`), and `location` is a free-text string, not the `{line_start,
   line_end}` the `schema.py` TypedDict suggests. The lenient `loader.validate()` ignores
   both, so it passes — but the Builder should normalize to one shape while relabeling
   (add `name`; either drop the typed `MutationLocation` or populate it).
5. **Infra reachable; tags pullable (verified via `docker manifest inspect`).** Docker
   27.3.1 is up; `grafana/grafana:13.0.2` is running with **20 cached p1 captures** under
   `results/<capture>/13.0.2/grafana-p1-seed-v1/` (reuse these). `postgres:17-alpine`,
   `redis:7-alpine`, `valkey/valkey:8.0-alpine` are already local. Keycloak 26.4.x/26.5.0
   and NetBox v4.4.x/v4.5.0 images pull cleanly (table in §3).
6. **The two measurement debts are real and share one fix.** `metrics.score_extraction`
   uses a 0.6 word-overlap matcher (open #3: under-reports ~92% semantic recall as ~12%);
   `metrics.score_verdicts` maps verdict→GT by exact `claim_id`, which only aligns at `c1`
   for E2E runs (open #4). **Both are solved by one semantic claim-matcher in
   `metrics.py`** (§4).
7. **Leakage-guard tripwire for Builders.** `tests/test_leakage_guards.py` greps the
   prediction modules for the literal tokens `is_correct`, `expected_findings`,
   `_load_ground_truth`, `MANIFEST_PATH`, and the whole word `mutation`. Generalization
   code in `extract/plan/drive/verify` **must not introduce any of these strings** —
   notably, do not read the manifest from a prediction module and do not write the word
   "mutation". Product/page/content are *prediction inputs* the orchestrator forwards;
   GT labels are not.

**Net effect:** the experiment is closer to done than WORKFLOW.md implies on *authoring*,
and further on *validation + generalization + measurement*. The plan is sequenced
accordingly: cheap re-score/relabel where the draft already holds, real work where the
deployed build hasn't been consulted.

---

## 1. Workstream 1 — Dataset authoring (audit/relabel against the deployed build)

### 1.1 The matrix is already met — adopt it, don't rebuild it

The drafted per-page mutation assignment (verified from the manifest) is sensible and
hits the `dataset-plan.md` sample-size table exactly. **Builders adopt this mapping**;
do not renumber or move mutations between pages without a recorded reason.

| Page (each product) | Page type | Mutations present | Count |
|---|---|---|---|
| `p1` | procedural | M1, M2, M3, M4, M5, M6 | 6 |
| `p2` | procedural | M1, M2, M3, M4, M7 | 5 |
| `p3` | reference | M1, M3, M4, M5, M6, M7 | 6 |
| `p4` | reference | M1, M2, M3, M4, M5, M6 | 6 |
| `p5` | descriptive | M1, M3, M4, M5, M6, M7 | 6 |

Per product: **5 clean + 29 mutated = 34 entries**. Three products = **102 entries**.
Column totals per product: M1=5, M2=3, M3=5, M4=5, M5=4, M6=4, M7=3 → **87 mutations**.
✔ matches `dataset-plan.md`. (M2 sits on the procedural/ordered-reference pages p1/p2/p4;
M7 stale-terminology on the reference/descriptive pages p2/p3/p5 — both well-placed.)

### 1.2 Per-entry labeling protocol (run during each product's Stage-2 Build)

For every entry of the product being built, label **against the running, pinned build**
(the same build the Driver will use — version equality is enforced, §3). Per entry:

1. **Pin the version.** Set `product_version` = that product's `config` version (§3),
   plus `labeled_against_version` (same string) and `labeled_by` (e.g.
   `"planner+executor, deployed-build audit, 2026-06-18"`). This makes Fix-1 preflight
   meaningful for all entries, not just grafana-p1.
2. **Audit each clean claim against the deployed UI.** A claim that the deployed product
   contradicts is relabeled `is_correct=false` **with a `provenance` string** (L6) citing
   the concrete UI evidence (screen + what was observed). Expect real drift to surface on
   the not-yet-audited pages, exactly as it did for grafana-p1 (c3/c5/c9/c12). `is_correct`
   stays **decoupled** from `is_mutated` (see memory: GT is_correct independent of mutation).
3. **Confirm each mutation is OBSERVABLE.** For every mutated entry, verify the injected
   contradiction is a *detectable* difference in the deployed product (the M1 lesson). If
   it is not observable as drafted (the borderline cases in §0.3), **redesign the mutation**
   to a real, detectable contradiction on the same page/claim, preserving the M-type
   intent, and record the redesign in the per-product results doc (mirror
   `PLAN_gt-relabel-and-m1-redesign.md`). Keep `affected_claim_ids == expected_findings`
   and ensure every `expected_finding` claim is `is_correct=false` (validator enforces).
4. **Normalize the mutation object** while you're there: ensure `type`, `name`,
   `description`, `original_text`, `mutated_text` (≠ each other), `affected_claim_ids`.
   Pick one `location` convention and apply it consistently.
5. **Keep claim text aligned to the (mutated) doc.** In a mutated entry, the affected
   claim's text should reflect what the *mutated* doc now asserts (several drafted entries
   left the pre-mutation text). This matters for E2E alignment (§4) and honest scoring.

**Descriptive-page caveat (call out, don't hide):** many descriptive-page claims are
conceptual/behavioral statements with no single product *screen* (e.g. netbox-p5 "Each
VRF is assigned a route distinguisher"). These will legitimately resolve to
`UNCERTAIN`/abstain under a UI-only verifier. That is honest behavior, not a bug — record
the abstention rate per page type; do not contort the fixture to force a verdict.

### 1.3 Invariants this workstream must honor

- **L1:** all labeling lives in the manifest + `metrics.py`; never feed labels to a
  prediction module. **L6:** every non-mutation `is_correct=false` carries `provenance`.
  **Observable mutations:** §1.2.3. **Version pinning:** §1.2.1 == §3.

---

## 2. Workstream 2 — Pipeline generalization (Grafana path → product-parametric)

**Principle:** make the product a *parameter*, reusing the Grafana code as the template.
The orchestrator already forwards `(product, page_id, content)` as prediction inputs and
delegates all scoring to `metrics.py`; keep it that way. **No prediction module may gain
any forbidden token (§0.7).** Each phase receives `product` from its caller; **version
comes from `config`, never from the manifest** (so drive/verify stay GT-blind and Fix-1
equality is config↔manifest).

### 2.1 Generalization surface (exact files + how)

| File | Today (Grafana-hardcoded) | Generalize to | How (minimal, idiomatic) |
|---|---|---|---|
| `pipeline/config.py` | single `PRODUCT_VERSION`, `GRAFANA_*` (image/container/port/url/creds), single `FIXTURE_ID` | a `PRODUCTS: dict[str, ProductSpec]` registry | Add a frozen `ProductSpec` dataclass (`name, version, image, container, port, url, health_url, version_probe, user, pass, fixture_id, ontology_path`). Keep `GRAFANA_*` as thin aliases of `PRODUCTS["grafana"]` so nothing breaks mid-migration. `capture_subdir` gains a `product` arg → `base/<product>/<version>/<fixture>/` (prevents cross-product collisions). |
| `pipeline/ontology.py` | hardcoded `ONTOLOGY_PATH = fixtures/grafana/...` | `normalize(screen, product, threshold)` loads `fixtures/<product>/screen_ontology.json` (lru-cache per product) | One extra arg threaded from `extract.run(...)`. Heuristics/threshold are a **frozen judgment knob** (§4). |
| `pipeline/extract.py` | `ontology.normalize(c.target_screen)` | pass `product` through to `ontology.normalize` | One-line change; `run()` already has `product`. |
| `pipeline/plan.py` | hardcoded `GRAFANA_P1_DEPS`, Grafana `_build_product_context()` | **derive the dependency graph from the ontology's `parent` field** (the Grafana ontology already encodes every parent) + product-parametric context | Replace `GRAFANA_P1_DEPS` with `deps_from_ontology(product)` reading `parent` links — unifies ontology+depgraph into ONE per-product artifact, deletes duplicated maps. `_build_product_context(product)` pulls name/url/creds from `ProductSpec`. |
| `pipeline/drive.py` | `start_grafana`/`wait_for_grafana`/`get_grafana_version`/`assert_version`/`pre_auth`/`provision_fixture` all Grafana-specific; `run(dataset_id)` | a small per-product **infra adapter** selected by `product` (passed in); `run(dataset_id, product)` | See §2.2. Keep helper names generic (`start_product`, `assert_version(product)`). Must avoid forbidden tokens. |
| `pipeline/orchestrator.py` | `main()` literal `dataset_ids=["grafana-p1-clean","grafana-p1-m1"]` | iterate the manifest filtered to the active product; forward `product` into every phase; pass the §4 alignment into scoring | Replace the literal list with `loader.filter_by(load(), product=<arg>)` ids (reads prediction inputs only — already permitted in orchestrator). Add a `--product` / per-product loop. Per-entry try/except already isolates failures. |
| `pipeline/prompts/` | `fixture_setup.txt` Grafana-specific; extract/verify product-neutral | per-product `fixture_setup_<product>.txt`; keep extract/verify/decompose/agent_system **product-neutral and FROZEN** | Only the fixture-setup prompt is product-specific. The judgment-bearing prompts stay shared (§5 freeze). |
| `fixtures/<product>/` | only `grafana/` exists | add `keycloak/` and `netbox/` (`screen_ontology.json` + optional seed fixture + README) | Ontologies built by a **claim-blind UI crawl** of the deployed product (L5) — never from `manifest.jsonl`. |
| `pipeline/models.py` | product-neutral already | unchanged | `ScreenState`/`DriverPlan`/`NavigationTrace`/`Verdict` need no change. |

### 2.2 The drive-phase infra adapter (the biggest surface)

Each product differs in bring-up and version probe. Encapsulate per product; select by the
`product` arg (GT-blind):

- **Bring-up:** Grafana = `docker run` (exists); Keycloak = `docker run … start-dev` with
  admin-bootstrap env; NetBox = **`docker compose up`** (multi-container) — vendor a pinned
  `fixtures/netbox/docker-compose.yml` (or clone `netbox-community/netbox-docker` at a tag
  matched to the app version) and shell out to `docker compose`.
- **Health + version probe (generalize `get_*_version`/`assert_version`):**
  - Grafana → `GET /api/health` → `.version` (exists).
  - NetBox → `GET /api/status/` → `.["netbox-version"]` (public JSON).
  - Keycloak → obtain an admin token (`admin-cli` against master realm via the token
    endpoint), then `GET /admin/serverinfo` → `.systemInfo.version`; **fallback** = scrape
    the welcome page version or `docker inspect` the pinned image tag. `assert_version`
    compares the probe to `ProductSpec.version` and **aborts on mismatch** (Fix 1).
- **Pre-auth:** Grafana admin/admin; Keycloak admin/admin at `/admin`; NetBox superuser
  from compose env (`SUPERUSER_*`) / API token.
- **Fixture provisioning (L3-clean — derived from screens-to-reach, never the answer key):**
  Grafana = existing seed dashboard; Keycloak = a seed realm + user/group so reference/admin
  screens are reachable; NetBox = a seed site/manufacturer/device so DCIM/IPAM list & detail
  screens are reachable. Non-fatal, idempotent, UI-driven (MISSION UI-only boundary).
- **Captures** remain a pure function of `(product, version, fixture_id, screen_id)` (L3/L7);
  verdicts/claims/plans stay flat. Pass-B replays stay additionally keyed by `dataset_id`.

### 2.3 L1 must keep passing — the standing constraint

After every Builder edit, `tests/test_leakage_guards.py` and
`dataset.loader.validate(load())` **must pass before reporting SUCCESS**. `metrics.py`
stays the sole reader of `is_correct`/`expected_findings`/`mutation`/`provenance`. If a
generalization seems to *need* a prediction module to read GT or the manifest, that is a
design smell — pass the datum in as a prediction input instead, or move the logic to
`metrics.py`/the orchestrator.

---

## 3. Workstream 3 — Per-product infra (pinned versions + generalized preflight)

All tags below **verified pullable this session** via `docker manifest inspect`. The
Driver confirms the exact running build via the §2.2 probe and sets `config` +
`product_version` labels to match (deployed == labeled).

| Product | Image (pinned) | Bring-up | Version probe | Default creds |
|---|---|---|---|---|
| **Grafana** | `grafana/grafana:13.0.2` *(running, validated)* | `docker run -d -p 3000:3000` | `GET /api/health`→`version` | admin/admin |
| **Keycloak** | `quay.io/keycloak/keycloak:26.4.0` *(26.4.1/26.4.2/26.4.4/26.5.0 also pullable)* | `docker run -p 8080:8080 -e KC_BOOTSTRAP_ADMIN_USERNAME=admin -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin quay.io/keycloak/keycloak:26.4.0 start-dev` | admin token → `GET /admin/serverinfo`→`systemInfo.version` | admin/admin |
| **NetBox** | `docker.io/netboxcommunity/netbox:v4.4.0` *(v4.4.1–v4.4.3/v4.5.0 also pullable)* + `postgres:17-alpine` + `valkey/valkey:8.0-alpine` *(or `redis:7-alpine`)* — all pullable/local | `docker compose up -d` (vendored/pinned compose: NetBox + Postgres + cache) | `GET /api/status/`→`netbox-version` | superuser from compose env |

Notes:
- **Keycloak version pin:** 26.x is required because `dataset-plan.md`'s bring-up uses
  `KC_BOOTSTRAP_ADMIN_*` (introduced in 26.0, replacing `KEYCLOAK_ADMIN*`). 26.4.0 is a
  mature minor; bumping within 26.4.x (or to 26.5.0) is mechanical and allowed — just keep
  config == manifest label.
- **NetBox compose:** prefer the official `netbox-community/netbox-docker` compose pinned
  to a release compatible with the app image (it already pins Postgres + cache); vendor the
  exact file under `fixtures/netbox/` so the run is reproducible. `dataset-plan.md` says
  "Postgres + Redis"; current netbox-docker uses **valkey** (a Redis-compatible fork) —
  either is fine; pin whatever the chosen netbox-docker tag ships.
- **Generalized preflight:** `drive.assert_version(product)` refuses to drive unless the
  probe equals `ProductSpec.version`; this is the per-product equivalent of the existing
  Grafana guard and is non-negotiable.

---

## 4. Workstream 4 — Measurement fixes (one semantic matcher solves #3 and #4)

Both open items reduce to "match an extracted/predicted claim to its ground-truth claim by
*meaning*, not by string overlap or coincidental ID." Build **one** primitive in
`metrics.py` (the sole GT reader — so this stays L1-clean) and use it twice.

### 4.1 Semantic claim matcher (new, in `metrics.py`)

- `semantic_match(extracted: list[dict], gt_claims: list[dict]) -> dict[ext_id → gt_id]`:
  an **LLM-judge** matcher via `claude -p` (`--model haiku`, `--output-format json`) that,
  for each GT claim, picks the best-expressing extracted claim (or none). Stays inside the
  `claude -p` constraint (no SDK/embeddings). Keep the 0.6 word-overlap as a cheap
  pre-filter / tie-break and as an offline fallback when the CLI is unavailable.
  Deterministic-leaning prompt; cache the decision per `(dataset_id)` so it is computed once
  and re-used by both consumers. `claude_runner` import into `metrics.py` is acyclic.
- **#3 fix:** `score_extraction` uses the semantic matcher for the match set; recall =
  matched/|GT|, precision = matched/|extracted|, type & attribution measured over matches.
  **Calibration gate:** on `grafana-p1-clean` it must report recall in the ~0.9 range
  (the known ~92% semantic recall), not ~0.12. Verify on a DEV page before trusting it.
- **#4 fix:** add an optional `alignment: dict[ext_id→gt_id]` arg to `score_verdicts`;
  when present (E2E path), map each verdict's extracted-claim-id to its GT id before the
  confusion matrix. Unmatched **extracted** claims (no GT) → reported as extraction false
  positives, **not** verification FP; unmatched **GT** claims (extraction miss) →
  `no_verdict`/coverage gap, **not** FN (a missed *contradiction* requires a wrong verdict,
  not a missing extraction). The orchestrator passes the alignment for non-oracle runs; the
  oracle path keeps identity alignment. **Result: E2E confusion matrices become trustworthy
  for all products** (resolves the "oracle-only" caveat), so the headline FN-per-mutation-type
  numbers are honest.

### 4.2 DEV/TEST split (L4) — **recommended: DEV = Grafana + Keycloak; TEST = NetBox**

I endorse the workflow's default, justified by the evidence:
- **Grafana** is already validated; its quirks (editions gap, Dynamic Dashboards) are known
  — the natural DEV anchor and the only product with cached captures.
- **Keycloak** as the second DEV product adds a *different* doc format (AsciiDoc) and UI
  pattern (admin console, role/permission-heavy) to tune the semantic matcher, ontology
  heuristics, and verify behavior against — so tuning isn't overfit to Grafana alone.
- **NetBox** is the most different (RST/MkDocs docs; DCIM/IPAM CRUD; form-heavy) → the
  strongest generalization test. Held out, **run once**, with judgment knobs **frozen**.
- Split size: DEV = 2×34 = 68 entries (10 clean + 58 mutated); TEST = 1×34 = 34 (5 clean +
  29 mutated) ≈ 67/33. Adequate for both tuning and a held-out estimate.

**Frozen for TEST (judgment-bearing knobs)** — declared in a `FROZEN_KNOBS.md` written
*after* Keycloak's Stage-3 and *before* NetBox's Stage-2 (so the freeze is auditable):
extract/verify/decompose prompt templates; the semantic-matcher prompt + thresholds;
`ontology.normalize` heuristics/threshold; `VERIFY_SELF_CONSISTENCY_N`, the majority-vote
rule, and `uncertain`/confidence handling; `IMAGE_INPUT_ENABLED`.
**Allowed for TEST (mechanical enablement only):** NetBox's image tag, URL, credentials,
container/compose bring-up, version probe, `screen_ontology.json` (claim-blind crawl),
seed fixture, and dependency graph (derived from its ontology). No re-tuning on TEST; no
peeking at TEST scores to adjust a frozen knob.

---

## 5. Workstream 5 — Run + analysis order (keyed to workflow stage IDs)

Sequential, gated, product-sharded (Grafana → Keycloak → NetBox), resumable via
`results/_workflow/PROGRESS.md`. One product fully through Build→Drive before the next.

| Stage ID | Role | Scope | Key deliverable / gate |
|---|---|---|---|
| `01-plan` | Planner | this file | ✔ this plan exists; status `SUCCESS` |
| `02-grafana-build` | Builder | **Generalize the pipeline product-parametrically (§2) using Grafana as template**; build the §4 semantic matcher + alignment; audit/relabel grafana p2–p5 + all grafana mutations vs deployed 13.0.2 (§1.2); calibrate the matcher on grafana-p1 | manifest valid + L1 passes; matcher calibration gate met |
| `03-grafana-drive` | Driver | Reuse Grafana 13.0.2 + cached p1 captures; provision fixtures; run all **34** grafana entries through 4 phases; score via `metrics.py` | per-product results section (FP-clean, FN per M-type, nav success, attribution, cost) |
| `02-keycloak-build` | Builder | **Mechanical enablement** of Keycloak (config/spec, ontology via claim-blind crawl, fixture, deps, preflight probe) + audit/relabel keycloak entries vs deployed 26.4.x; **finalize matcher/knob tuning (last DEV product)** | manifest valid + L1 passes |
| `03-keycloak-drive` | Driver | Bring up Keycloak 26.4.x (preflight); run all **34** keycloak entries; score | keycloak results section |
| **— FREEZE —** | Builder/Driver | Write `FROZEN_KNOBS.md` (§4.2). After this, no judgment knob changes. | freeze recorded |
| `02-netbox-build` | Builder | **Mechanical enablement ONLY** of NetBox (image/url/creds/compose/ontology/fixture/deps/probe); label GT vs deployed v4.4.x with provenance; **no frozen-knob edits** | manifest valid + L1 passes; diff touches no frozen knob |
| `03-netbox-drive` | Driver | Bring up NetBox compose (preflight); run all **34** netbox entries **once**; score. No re-tuning. | netbox results section |
| `04-analyze` | Analyst | Aggregate headline metrics via `metrics.py` under the DEV/TEST split: extraction recall, **FP rate (clean)**, **FN rate per mutation type M1–M7** (the priority), navigation success, attribution accuracy; per-product + cross-product tables; total cost; honest limitations | `RESULTS_full-experiment.md`; refreshed `CLAUDE.md` status |

**Cost / effort controls:** Pass-A captures are claim-blind → drive each *page* once and
reuse across its clean + all mutations (the m1 re-run was verify-dominated and cheap for
exactly this reason). Prefer **re-score over re-run** wherever outputs already exist
(grafana-p1 is done). Per-entry try/except keeps one failure local. Drivers checkpoint into
`PROGRESS.md` and report `BLOCKED — context` if near the limit; the orchestrator relaunches.

**Results-doc template:** follow `RESULTS_remediation-run.md` (Headline → scorecard →
phase-by-phase → verifier analysis → per-M-type detection → bugs fixed → cost → artifacts);
each Driver appends its product section; the Analyst writes the cross-product roll-up.

---

## 6. Risks & how the plan handles them

- **Borderline-observable mutations (§0.3)** → §1.2.3 observability audit + M1-style
  redesign, recorded with provenance. The single biggest quality risk; budget time for it.
- **Descriptive-page conceptual claims** → expect/Report higher `UNCERTAIN`; do not force
  verdicts. A real, honest limitation for a UI-only verifier.
- **Keycloak version probe** has no clean unauthenticated endpoint → token+`serverinfo`
  with documented fallbacks (§2.2).
- **NetBox multi-container bring-up** is heavier than `docker run` → vendor a pinned compose
  file; treat as mechanical infra (allowed even for the TEST product).
- **Semantic matcher cost/nondeterminism** → haiku + word-overlap pre-filter + per-dataset
  caching; calibrate on DEV; freeze before TEST.
- **Accidental L1 regression during generalization** → run `tests/test_leakage_guards.py`
  after every edit; never let a forbidden token (§0.7) into a prediction module.

---

## 7. Definition of done (for the chain)

The full 102-entry dataset runs through all four phases on per-product correctly-pinned
infra; `metrics.py` reports extraction recall, FP-rate on clean pages, and **FN rate per
mutation type (M1–M7)** under the **DEV (Grafana+Keycloak) / TEST (NetBox, frozen, run
once)** split; `tests/test_leakage_guards.py` and `loader.validate()` pass throughout;
`RESULTS_full-experiment.md` records per-product + cross-product tables, total cost, and an
honest limitations section. That is the experiment `MISSION.md` describes — not a
single-page demonstration.

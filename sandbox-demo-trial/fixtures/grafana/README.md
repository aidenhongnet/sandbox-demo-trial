# Grafana p1 fixtures (Fix 5)

Deterministic, ephemeral environment state so the complex-state screens in
`p1_create_dashboard` are reachable. A fresh Grafana container has no dashboards,
so 6 screens failed in the first run and 9 clean claims were stuck UNCERTAIN
("No screen state captured"). This fixture provides the missing preconditions.

## Leakage guard L3

The fixture is derived **only from the list of screens to reach** — never from
`is_correct` / `expected_findings`. It is a pure function of
`(product_version, fixture_id, screen_id)`, so one capture is safely reused
across `*-clean` and every mutation of the same page. Captures live under
`results/<capture>/<product_version>/<fixture_id>/` (see `config.capture_subdir`).
Bump `config.FIXTURE_ID` whenever this definition changes.

## What `p1_seed_dashboard.json` provides

A saved dashboard (`uid: mvp-p1-seed`) with:
- **4 panels** (timeseries / stat / timeseries / gauge) using the built-in
  `-- Grafana --` random-walk source, so they render with no external data setup.
- **1 row** ("Overview").
- **2 template variables** — `server` (multi-value, includeAll) and
  `environment` (single-value).

This unlocks, by itself: `content-outline` (needs panels/rows/variables),
`dashboard-settings-layout`, `panel-sidebar-repeat-options` (needs a variable),
`dashboard-edit-mode-panel-drag` / `-panel-resize` (need >1 panel).

## Setup the provisioner performs (UI-only, setup-only)

`drive.provision_fixture()` (run during `--setup`) establishes the state through
the **rendered UI** so even setup is user-perspective (MISSION boundary):

1. Import the dashboard via **Dashboards → New → Import** and paste this JSON
   (or the per-file path). Idempotent: overwrites `uid: mvp-p1-seed`.
2. Switch the dashboard layout to **Auto grid** (Dashboard options → Layout),
   which unlocks `auto-grid-layout-settings` and makes **Show/hide rules**
   available (they exist only in Auto grid).
3. Add a **Template variable** show/hide rule and a second rule so the
   **Match rules** control appears — unlocking
   `showhide-rules-template-variable-rule` and `showhide-rules-match-rules`.

Grafana file-provisioning is the fallback only if UI import is unavailable; it is
clearly **setup-only** and never used for verification.

## DRIVER note

This JSON is a **classic-schema** dashboard; Grafana 13 migrates it to the new
dynamic-dashboard model on import. Verify it imports cleanly on `13.0.2` and that
steps 2–3 succeed in the live UI; if the new-schema (v2) import is preferred,
**export** the established dashboard from 13.0.2 and replace this file, then bump
`FIXTURE_ID`. Whether each screen exists at all is governed by Fix 1
(deployed == labeled version).

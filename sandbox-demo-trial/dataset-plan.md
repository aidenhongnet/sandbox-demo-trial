# Dataset Plan

## Target Products

| Product  | Repo                      | Doc style                                                  | Run locally                                                                                                                             |
| -------- | ------------------------- | ---------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Grafana  | `grafana/grafana`         | Markdown, screenshot-heavy, procedural + reference         | `docker run -d -p 3000:3000 grafana/grafana`                                                                                            |
| Keycloak | `keycloak/keycloak`       | AsciiDoc, dense reference, role/permission-heavy           | `docker run -p 8080:8080 -e KC_BOOTSTRAP_ADMIN_USERNAME=admin -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin quay.io/keycloak/keycloak start-dev` |
| Netbox   | `netbox-community/netbox` | reStructuredText/MkDocs, inventory/DCIM domain, form-heavy | Docker Compose via `netbox-community/netbox-docker`                                                                                     |

Diversity: three doc formats, three domains, three UI patterns (dashboards vs. admin console vs. inventory CRUD).

## Doc Pages Per Product

Select 3-5 pages per product covering:
- Procedural (how-to with explicit steps)
- Reference (settings, fields, defaults)
- Descriptive (overview, dashboard, conceptual)

## Sample Sizes

| Category | N per product | Total |
|----------|---------------|-------|
| Clean (unmutated) pages | 5 | 15 |
| M1 — Wrong nav path | 5 | 15 |
| M2 — Wrong step order | 3 | 9 |
| M3 — Nonexistent UI element | 5 | 15 |
| M4 — Wrong field name | 5 | 15 |
| M5 — Wrong default value | 4 | 12 |
| M6 — Wrong behavior description | 4 | 12 |
| M7 — Stale terminology | 3 | 9 |

Total mutations: ~87. Total pages including clean controls: ~102.

## Mutation Types

| ID  | Name                   | Description                                                                               |
| --- | ---------------------- | ----------------------------------------------------------------------------------------- |
| M1  | Wrong nav path         | Navigation instructions point to a menu/screen path that doesn't exist or leads elsewhere |
| M2  | Wrong step order       | Procedural steps are reordered so the sequence fails or produces wrong state              |
| M3  | Nonexistent UI element | Doc references a button, link, or control that isn't present on the screen                |
| M4  | Wrong field name       | Doc uses a label that doesn't match the actual field label in the UI                      |
| M5  | Wrong default value    | Doc states a default setting value that differs from the actual default                   |
| M6  | Wrong behavior         | Doc describes an outcome or side effect that doesn't match what the product does          |
| M7  | Stale terminology      | Doc uses outdated product terminology that has been renamed in the current version        |
|     |                        |                                                                                           |

## Ground Truth

Per page, human labels before mutations:
- Every verifiable claim
- Claim type: `nav_path | ui_element | field_value | behavior | visual_state`
- Target screen in the product

## Metrics

| Metric                    | Source                                         |
| ------------------------- | ---------------------------------------------- |
| Claim extraction recall   | Human labels vs extracted (clean pages)        |
| FP rate                   | Findings on clean pages                        |
| FN rate per mutation type | Missed mutations on mutated pages              |
| Navigation success        | % of claims where agent reached correct screen |
| Attribution accuracy      | % of claims matched to correct screen          |

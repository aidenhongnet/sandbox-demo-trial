# Documentation Quality Evaluation Dataset

Labeled evaluation dataset for testing automated documentation quality checkers. Contains 102 documentation pages (15 clean + 87 mutated) across three open-source products, with ground-truth annotations for verifiable claims and intentional contradictions.

## Schema

Each entry in `manifest.jsonl` is a JSON object with:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique entry ID: `{product}-p{N}-{clean\|m1..m7}` |
| `product` | string | `grafana`, `keycloak`, or `netbox` |
| `page_id` | string | Source page reference: `{product}-p{N}` |
| `page_type` | string | `procedural`, `reference`, or `descriptive` |
| `page_title` | string | Human-readable page title |
| `source_url` | string | Original documentation URL |
| `doc_format` | string | `markdown` or `asciidoc` |
| `content` | string | Full page text (clean or mutated) |
| `is_mutated` | bool | Whether this entry contains a mutation |
| `mutation` | object\|null | Mutation details (null for clean entries) |
| `claims` | array | Verifiable claims extracted from the page |
| `expected_findings` | array | Claim IDs a perfect checker would flag |

### Mutation Object

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | `M1`–`M7` mutation category |
| `name` | string | Short snake_case descriptor |
| `description` | string | What was changed |
| `original_text` | string | Exact text before mutation |
| `mutated_text` | string | Exact text after mutation |
| `location` | object | `{line_start, line_end}` in the content |
| `affected_claim_ids` | array | Claim IDs invalidated by this mutation |

### Claim Object

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique claim ID: `{page_id}-c{N}` |
| `text` | string | The claim assertion |
| `type` | string | `nav_path`, `ui_element`, `field_value`, `behavior`, or `visual_state` |
| `target_screen` | string | Which product screen this claim references |
| `is_correct` | bool | `false` if corrupted by a mutation |
| `line_number` | int | Source line number |

## Usage

```python
import dataset

entries = dataset.load()
grafana_mutated = dataset.filter_by(entries, product="grafana", is_mutated=True)
print(dataset.stats(entries))
errors = dataset.validate(entries)
```

## Mutation Types

| Type | Name | Count | Description |
|------|------|-------|-------------|
| M1 | Wrong nav path | 15 | One menu/path segment changed to a plausible but incorrect item |
| M2 | Wrong step order | 9 | Two adjacent procedural steps swapped where order matters |
| M3 | Nonexistent UI element | 15 | Button/tab/control replaced with a plausible but nonexistent name |
| M4 | Wrong field name | 15 | Form field label changed to a similar but incorrect label |
| M5 | Wrong default value | 12 | Default value changed to another plausible value |
| M6 | Wrong behavior | 12 | Action outcome changed to something plausible but incorrect |
| M7 | Stale terminology | 9 | Current term replaced with an outdated or cross-product term |

## Statistics

```
Total entries:     102
  Clean:            15  (14.7%)
  Mutated:          87  (85.3%)

By product:
  grafana:          34  (5 clean + 29 mutated)
  keycloak:         34  (5 clean + 29 mutated)
  netbox:           34  (5 clean + 29 mutated)

By page type:
  procedural:       39
  reference:        42
  descriptive:      21

Total claims:     1854
By claim type:
  behavior:        1011
  field_value:      424
  ui_element:       273
  nav_path:          79
  visual_state:      67
```

## Source Pages

### Grafana (Markdown)
| Page | Type | Title |
|------|------|-------|
| p1 | Procedural | Create dashboards |
| p2 | Procedural | Configure contact points |
| p3 | Reference | Configure Grafana (grafana.ini) |
| p4 | Reference | Configure standard options |
| p5 | Descriptive | Intro to Grafana Alerting |

### Keycloak (AsciiDoc)
| Page | Type | Title |
|------|------|-------|
| p1 | Procedural | Creating a Realm |
| p2 | Procedural | Creating Users |
| p3 | Reference | Password Policies |
| p4 | Reference | Session and Token Timeouts |
| p5 | Descriptive | Core Concepts and Terms |

### NetBox (Markdown)
| Page | Type | Title |
|------|------|-------|
| p1 | Procedural | Populating Data |
| p2 | Procedural | Planning Your Move |
| p3 | Reference | Device |
| p4 | Reference | Prefix |
| p5 | Descriptive | IPAM Overview |

## File Structure

```
dataset/
├── __init__.py          # Exports: load(), filter_by(), stats(), validate()
├── schema.py            # TypedDict definitions
├── loader.py            # Dataset loading, filtering, validation
├── manifest.jsonl       # The dataset (102 JSON lines)
├── sources/             # Raw fetched documentation (provenance)
│   ├── grafana/         # 5 Markdown files
│   ├── keycloak/        # 5 AsciiDoc files
│   └── netbox/          # 5 Markdown files
└── README.md            # This file
```

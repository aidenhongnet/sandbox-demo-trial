# Plan: MVP Verification Pipeline

## Objective

Prove end-to-end that the three core pipeline stages work: claim extraction, UI-driven state capture, and automated verification. The goal is not coverage — it's validating that each component functions and produces usable output before investing in scale.

## MVP Scope

**Product:** Grafana (simplest Docker setup: single `docker run` command, no compose or bootstrapping)
**Pages:** `p1_create_dashboard.md` (procedural, 25 claims, ~17 unique target screens)
**Dataset entries:** `grafana-p1-clean` + `grafana-p1-m1` (clean baseline + one mutation to test detection)
**Target:** Extract claims independently, drive the Grafana UI to capture screen states, verify claims, then compare against ground truth in `manifest.jsonl`.

Why Grafana p1: it exercises all five claim types (`nav_path`, `ui_element`, `field_value`, `behavior`, `visual_state`), hits 17 distinct screens, and the mutation (M1: wrong nav path — "Home" instead of "Dashboards") is unambiguous to detect. If the pipeline works here, the architecture generalizes to Keycloak/NetBox.

---

## Architecture

All model invocations use `claude -p` (Claude Code programmatic mode) instead of direct API calls. No Anthropic SDK. The orchestrator is a Python script that shells out to `claude -p` with the appropriate `--model` flag and parses JSON from stdout.

Browser interaction uses the `chrome-devtools` MCP server, giving Claude direct DOM-level tools (navigate, click, type, screenshot) through the standard MCP tool interface — no pixel-coordinate computer use, no Playwright.

```
Source Doc
    │
    ▼
┌──────────────────────────────────┐
│  Phase 1: Extract                │  claude -p --model haiku
│  Doc → atomic claims             │
└──────────────┬───────────────────┘
               │ claims[]
               ▼
┌──────────────────────────────────┐
│  Phase 2: Plan                   │  claude -p --model sonnet
│  Claims → driver plans           │
│  grouped by target screen        │
└──────────────┬───────────────────┘
               │ driver_plans[]
               ▼
┌──────────────────────────────────┐
│  Phase 3: Drive                  │  claude -p --model sonnet
│  Autonomous navigation via       │  + chrome-devtools MCP
│  chrome-devtools MCP tools       │
│  → screenshots + text descs      │
└──────────────┬───────────────────┘
               │ screen_states{}  (cached by target_screen)
               ▼
┌──────────────────────────────────┐
│  Phase 4: Verify                 │  claude -p --model haiku
│  Claim + screen state            │
│  → true/false                    │
└──────────────┬───────────────────┘
               │ verdicts[]
               ▼
           Report + metrics
```

---

## Phase 1: Claim Extraction

**Invocation:** `claude -p --model haiku --output-format json`
**Input:** Raw doc page text (from `dataset/sources/grafana/p1_create_dashboard.md`)
**Output:** List of atomic claims, each with:
- `text`: the assertion (phrased so it's either true or false)
- `type`: one of `nav_path | ui_element | field_value | behavior | visual_state`
- `target_screen`: which product screen to check
- `line_number`: source line reference

**Approach:**
1. Orchestrator reads the source doc and builds a prompt from `prompts/extract_claims.txt` + the doc content
2. Shells out: `claude -p --model haiku --output-format json < prompt.txt > results/claims/grafana-p1.json`
3. Instruct: "Extract every verifiable factual claim about the product's UI. Each claim must be testable by looking at the product. Do not extract opinions, recommendations, or external references."
4. Require JSON output matching the `Claim` schema (minus `id` and `is_correct` — those are assigned downstream)
5. Post-process in Python: assign claim IDs, deduplicate, validate types

**Evaluation:** Compare extracted claims against ground truth claims in `manifest.jsonl` for `grafana-p1-clean` (25 claims). Measure:
- Recall: how many ground truth claims are covered
- Precision: how many extracted claims are actually verifiable
- Type accuracy: how often the claim type matches

**Why Haiku:** This is structured text extraction — no complex reasoning. Haiku handles it at ~4x less cost than Sonnet with comparable quality for extraction tasks.

---

## Phase 2: Driver Plan Generation

**Invocation:** `claude -p --model sonnet --output-format json`
**Input:** Extracted claims grouped by `target_screen`
**Output:** Per screen group, a `DriverPlan` containing:
- `screen_id`: identifier matching the target_screen
- `starting_url`: where navigation begins (e.g., `http://localhost:3000`)
- `goal`: natural language description of the target screen state
- `navigation_hints[]`: high-level guidance (not scripts) for reaching the screen
  - e.g., "Navigate to the Dashboards section from the sidebar, create a new dashboard, then open a panel's repeat options"
- `what_to_capture`: what visual state to observe and record once there
- `required_preconditions[]`: any setup needed (e.g., "a dashboard must exist")
- `claim_ids[]`: which claims this plan serves
- `parent_screen_id`: if this screen is reachable from a previously-visited screen, reference it (enables branching from cached state)

The plans are **guidance for an autonomous agent, not executable scripts.** The `-p` agent driving chrome-devtools reads the plan and makes its own navigation decisions using MCP tools. This tests the core hypothesis: can an AI agent autonomously navigate a product UI from high-level instructions?

**Approach:**
1. Group the 25 claims by `target_screen` → ~17 screen groups
2. Sort groups by navigation depth (shallow screens first — their states may be preconditions for deeper ones)
3. Build a screen dependency graph so deeper screens can branch from cached parent states
4. For each group, send to Sonnet:
   - The claims targeting this screen
   - The product context (Grafana, localhost:3000, admin/admin credentials)
   - The claim types (so Sonnet knows whether we need to observe a static state or perform an action)
5. Sonnet outputs a structured plan with natural language navigation hints

**Screen dependency graph for Grafana p1:**
```
Home (localhost:3000)
  └── Dashboards list (click "Dashboards" in sidebar)
       └── New Dashboard (click "New" > "New Dashboard")
            ├── New Dashboard (edit mode) — default state
            ├── New panel options — click "Add new element" > Panel
            │    └── Panel edit mode — select "Configure visualization"
            │         ├── Panel edit mode - Queries tab
            │         ├── Panel edit mode - Visualization picker
            │         └── Panel editor > Standard options
            ├── Dashboard edit mode - toolbar — already visible in edit mode
            ├── Dashboard sidebar — already visible (docked by default)
            ├── Content outline — click Content outline icon
            ├── Dashboard settings - Layout — click Dashboard options icon
            │    └── Auto grid layout settings — select "Auto grid"
            ├── Panel sidebar - Repeat options — click panel, expand Repeat options
            ├── Panel sidebar - Show/hide rules — click panel, expand Show/hide rules
            │    ├── Show/hide rules - Template variable rule
            │    └── Show/hide rules - Match rules
            ├── Dashboard edit mode - Save menu — click Save dropdown
            └── Dashboard view mode - toolbar — click "Exit edit"
```

This DAG enables caching: navigate to "New Dashboard (edit mode)" once, then branch from that cached state to reach toolbar, sidebar, content outline, etc. ~8 unique root navigation paths cover all 17 screens.

**Why Sonnet:** This requires spatial reasoning about UI navigation, understanding of preconditions and state transitions. Haiku would produce unreliable navigation plans.

---

## Phase 3: Autonomous UI Driving (chrome-devtools MCP)

**Invocation:** `claude -p --model sonnet` with `chrome-devtools` MCP server enabled
**Input:** Driver plans from Phase 2
**Output:** Per target screen, a `ScreenState`:
- `screenshot_path`: path to PNG screenshot
- `text_description`: structured text representation of visible UI elements (produced by the agent during navigation)
- `url`: current URL at completion
- `navigation_log`: the `-p` session's MCP tool call trace
- `timestamp`: when captured

This is the core hypothesis test. The agent receives a high-level plan ("navigate to the panel edit mode's Queries tab") and must autonomously figure out what to click, where to look, and when it's arrived — using chrome-devtools MCP tools against the real product UI.

**Architecture: `claude -p` + chrome-devtools MCP**
```
┌──────────────────────────────────────────────────┐
│  Orchestrator (Python)                            │
│                                                   │
│  For each driver plan:                            │
│    Build prompt (plan + capture instructions)     │
│    Shell out: claude -p --model sonnet < prompt   │
│    Parse output: screenshot paths + text desc     │
└─────────────────┬────────────────────────────────┘
                  │
           claude -p (Sonnet)
           with chrome-devtools MCP
                  │
           ┌──────┴──────┐
           │  MCP tools: │
           │  navigate   │
           │  click      │
           │  type       │
           │  screenshot │
           │  evaluate   │
           └──────┬──────┘
                  │
           Chrome (--remote-debugging-port=9222)
                  │
           Grafana @ localhost:3000
```

Claude Code handles the full agent loop internally — MCP tool calls, observation, next-action decisions. No custom agent loop code. The orchestrator just fires `claude -p` per screen group and collects results.

**Approach:**
1. **Setup (once):**
   - Start Grafana: `docker run -d -p 3000:3000 --name grafana-mvp grafana/grafana`
   - Wait for readiness (poll `http://localhost:3000/api/health`)
   - Start Chrome with remote debugging: `chrome --remote-debugging-port=9222`
   - Verify chrome-devtools MCP server can connect
2. **Pre-auth (once):** Single `claude -p` call to log into Grafana (admin/admin) via MCP tools. Boring step — don't waste time testing it.
3. **For each driver plan (in dependency order):**
   a. Build prompt from `prompts/agent_system.txt` + the driver plan JSON
   b. Prompt tells the agent:
      - The goal screen to reach
      - Navigation hints from the plan
      - To use chrome-devtools tools to navigate
      - To take a screenshot when arrived at the target
      - To describe every visible UI element, label, button, field, value
      - To write the screenshot to `results/screenshots/{screen_id}.png`
      - To write the description to `results/descriptions/{screen_id}.txt`
   c. Shell out: `claude -p --model sonnet --allowedTools "mcp:chrome-devtools,Write,Read" < prompt.txt`
   d. Parse stdout for success/failure and paths to saved artifacts
4. **For `behavior` claims:** the prompt instructs the agent to perform the action and describe what changed (before/after)
5. **For branching from parent states:** Chrome is a long-lived process — the browser retains its state between `-p` calls. The orchestrator sequences plans along navigation paths so child screens run while the browser is still on the parent page. E.g., after navigating to "Dashboard edit mode," immediately run plans for toolbar, sidebar, content outline.

**State caching strategy:**
- **Browser persistence:** Chrome runs as a separate process. Between `-p` calls, it stays on whatever page the last call left it. The orchestrator exploits this by ordering plans along navigation paths — no re-navigation from scratch for child screens.
- **Result cache:** if a screen's screenshot + description already exist on disk, skip the `-p` call entirely.
- **Failure handling:** if a `-p` call fails to reach a screen (no screenshot written), log the failure and skip downstream dependents.
- **Reset between paths:** when switching to a different navigation path, one `-p` call navigates to the new root.

Navigation path ordering for Grafana p1:
```
Path 1: Home → Dashboards → New Dashboard (edit mode)
  branch: toolbar claims, sidebar claims, content outline claims
Path 2: (from edit mode) → Add panel → Panel edit mode
  branch: Queries tab, Visualization picker, Standard options
Path 3: (from edit mode) → Dashboard options → Layout settings
  branch: Auto grid settings
Path 4: (from edit mode) → Click panel → Repeat options, Show/hide rules
  branch: Template variable rule, Match rules
Path 5: (from edit mode) → Save dropdown
Path 6: (from edit mode) → Exit edit → View mode toolbar
```

~6 root navigations + ~11 branches = 17 screens. Branch screens start with the browser already positioned — the `-p` call just needs 1-3 MCP tool calls instead of a full navigation.

**Cost model:**
MCP tools operate at the DOM level (selectors, text content) — no screenshot tokens in the conversation, fewer roundtrips than pixel-coordinate computer use.
- Root navigations (~6): avg ~5 MCP tool calls each, ~3K tokens/call = ~90K input tokens
- Branch navigations (~11): avg ~2 MCP tool calls each, ~3K tokens/call = ~66K input tokens
- Text descriptions (17 screens): ~2K output tokens each = ~34K tokens
- Total input: ~156K tokens × $3/MTok = **~$0.47**
- Total output: ~68K tokens × $15/MTok = **~$1.02**
- **Phase 3 total: ~$1.49**

**Why chrome-devtools MCP:** DOM-level tools (click by selector/text, read page content) are more reliable and cheaper than coordinate-based computer use. For MVP, we're testing whether an AI agent can autonomously navigate from high-level plans — the navigation reasoning is what matters, not pixel targeting. Computer use can be evaluated later for products where DOM access isn't available.

---

## Phase 4: Claim Verification

**Invocation:** `claude -p --model haiku --output-format json`
**Input:** One claim + its corresponding screen state (text description, optionally screenshot)
**Output:** Per claim, a `Verdict`:
- `claim_id`: which claim
- `result`: `true | false | uncertain`
- `confidence`: float 0.0–1.0
- `reasoning`: brief explanation
- `evidence`: specific text/element from the screen state that supports the verdict

**Approach:**
1. For each claim, look up the cached `ScreenState` for its `target_screen`
2. **Text-first verification (cheap path):** Send claim + text description to Haiku
   - Prompt: "Given this description of a product screen, determine if the following claim is TRUE or FALSE. If you cannot determine from the description alone, respond UNCERTAIN."
3. **Image fallback (expensive path):** If Haiku returns `uncertain`, re-send with the screenshot attached
   - This should be needed for `visual_state` claims (colors, positions, layout) and some `ui_element` claims
4. Collect verdicts, compare against ground truth `is_correct` from manifest

**Verification by claim type:**
| Type | Primary method | Fallback |
|------|---------------|----------|
| `nav_path` | Text description (check URL, page title) | Screenshot |
| `ui_element` | Text description (check element names) | Screenshot |
| `field_value` | Text description (check field labels/values) | Screenshot |
| `behavior` | Text description (before/after states) | Screenshot pair |
| `visual_state` | Screenshot (colors, layout, icons) | N/A — always needs image |

**Why Haiku:** Binary classification with evidence is Haiku's sweet spot. At $0.80/MTok input, verifying 25 claims costs ~$0.05-0.10. With Sonnet it would be ~$0.20-0.40 for the same quality on this type of task.

---

## Model Selection Summary

All invocations via `claude -p`. No Anthropic SDK.

| Phase | Task | Invocation | Rationale |
|-------|------|-----------|-----------|
| 1 - Extract | Doc → claims | `claude -p --model haiku` | Structured extraction, no complex reasoning |
| 2 - Plan | Claims → driver plans | `claude -p --model sonnet` | UI navigation reasoning, state dependency planning |
| 3 - Drive | Autonomous UI navigation + state capture | `claude -p --model sonnet` + chrome-devtools MCP | Core hypothesis: autonomous agent navigates real UI from plan |
| 4 - Verify | Claim + state → verdict | `claude -p --model haiku` | Binary classification with evidence |

**Estimated MVP cost (Grafana p1, 25 claims):**
| Phase | Haiku cost | Sonnet cost | Total |
|-------|-----------|-------------|-------|
| 1 - Extract | ~$0.01 | — | $0.01 |
| 2 - Plan | — | ~$0.15 | $0.15 |
| 3 - Drive (MCP, 17 screens) | — | ~$1.49 | $1.49 |
| 4 - Verify (text-first) | ~$0.05 | — | $0.05 |
| 4 - Verify (image fallback, ~30%) | ~$0.10 | — | $0.10 |
| **Total** | **~$0.16** | **~$1.64** | **~$1.80** |

Phase 3 dominates cost (~83%). This is expected — autonomous navigation is the expensive part. MCP tools cut this roughly in half vs. coordinate-based computer use (no screenshot tokens in conversation, fewer roundtrips). Optimizations at scale: more aggressive state caching, smarter branching order.

---

## Implementation Steps

### Step 0: Project setup
- Create `pipeline/` directory with `__init__.py`
- Add `config.py` with Grafana Docker config, Chrome debugging port, model names, output paths
- Add `models.py` with Pydantic models: `ExtractedClaim`, `DriverPlan`, `ScreenState`, `Verdict`
- Add `requirements.txt`: `pydantic` (only Python dep — all model calls go through `claude -p`)
- Add `results/` directory with `screenshots/`, `descriptions/`, `navigation_logs/`, `verdicts/` subdirs
- Install chrome-devtools MCP server via bun
- Configure `.claude/settings.json`:
  ```json
  {
    "mcpServers": {
      "chrome-devtools": {
        "command": "bun",
        "args": ["run", "chrome-devtools-mcp"]
      }
    },
    "permissions": {
      "allow": ["mcp:chrome-devtools", "Write", "Read"]
    }
  }
  ```
- Verify: `claude -p "Use chrome-devtools to navigate to google.com and take a screenshot"` should work

### Step 1: Claim extraction (`pipeline/extract.py`)
- Load source doc from `dataset/sources/grafana/p1_create_dashboard.md`
- Build prompt: `prompts/extract_claims.txt` template + doc content → temp file
- Shell out: `claude -p --model haiku --output-format json < prompt.txt`
- Parse JSON stdout into `ExtractedClaim[]`
- Assign IDs, validate types
- Write to `results/claims/grafana-p1.json`
- **Smoke test:** compare count and types against manifest ground truth (25 claims)

### Step 2: Driver planning (`pipeline/plan.py`)
- Load extracted claims from `results/claims/grafana-p1.json`
- Group by `target_screen`
- Build prompt: `prompts/plan_navigation.txt` template + claims JSON
- Shell out: `claude -p --model sonnet --output-format json < prompt.txt`
- Parse into `DriverPlan[]`
- Write to `results/plans/grafana-p1.json`
- **Smoke test:** manually verify 2-3 plans describe sensible navigation paths

### Step 3: Autonomous driving (`pipeline/drive.py`)
The core component — but thin, because `claude -p` + MCP does the heavy lifting:
- Docker: start Grafana container, wait for health
- Chrome: start with `--remote-debugging-port=9222`, navigate to localhost:3000
- Pre-auth: `claude -p --model sonnet "Log into Grafana at localhost:3000 with admin/admin using chrome-devtools tools"`
- For each driver plan (in dependency order, following path ordering):
  - Build prompt: `prompts/agent_system.txt` template + plan JSON + output paths
  - Shell out: `claude -p --model sonnet --allowedTools "mcp:chrome-devtools,Write,Read" < prompt.txt`
  - Check if expected output files were created:
    - `results/screenshots/{screen_id}.png` — screenshot at target screen
    - `results/descriptions/{screen_id}.txt` — text description of visible UI
  - If files exist: success, continue to next plan
  - If missing: log failure from stdout, skip downstream dependents
  - Save stdout → `results/navigation_logs/{screen_id}.txt` for debugging
- **Smoke test:** open screenshots manually, verify they show the expected screens

### Step 4: Verification (`pipeline/verify.py`)
- Load claims from `results/claims/grafana-p1.json`
- Load screen descriptions from `results/descriptions/`
- For each claim:
  - Build prompt: `prompts/verify_claim.txt` template + claim JSON + matching screen description text
  - Shell out: `claude -p --model haiku --output-format json < prompt.txt`
  - Parse verdict from JSON stdout
  - If `uncertain`: rebuild prompt with screenshot path appended, re-run
  - Record verdict
- Write verdicts to `results/verdicts/grafana-p1.json`
- **Smoke test:** compare verdicts against `is_correct` ground truth

### Step 5: Orchestrator + report (`pipeline/orchestrator.py`)
- Wire phases 1-4 together
- Run end-to-end on `grafana-p1-clean` (expect all true)
- Run end-to-end on `grafana-p1-m1` (expect c1 flagged as false)
- Produce summary report:
  - Claim extraction: recall, precision, type accuracy vs. ground truth
  - Navigation: success rate (screens reached / screens attempted), avg steps per screen
  - Verification: accuracy, FP rate (clean), FN rate (mutated)
  - Cost: actual API tokens consumed per phase
  - Agent behavior: avg steps to reach screen, failure modes, fallback rate

---

## Data Models

```python
from pydantic import BaseModel
from typing import Literal

class ExtractedClaim(BaseModel):
    id: str
    text: str
    type: Literal["nav_path", "ui_element", "field_value", "behavior", "visual_state"]
    target_screen: str
    line_number: int

class DriverPlan(BaseModel):
    screen_id: str
    starting_url: str
    goal: str                          # natural language: what the agent should see when done
    navigation_hints: list[str]        # high-level guidance, not executable steps
    what_to_capture: str               # what to describe in the text representation
    preconditions: list[str]
    claim_ids: list[str]
    parent_screen_id: str | None       # branch from cached parent state if available

class ScreenState(BaseModel):
    screen_id: str
    screenshot_path: str
    text_description: str
    url: str
    timestamp: str
    navigation_log_path: str           # path to raw -p stdout for debugging
    success: bool

class Verdict(BaseModel):
    claim_id: str
    result: Literal["true", "false", "uncertain"]
    confidence: float
    reasoning: str
    evidence: str
    used_image_fallback: bool
```

---

## Risks & Open Questions

### Risks
1. **Grafana version mismatch.** The docs are for the latest Grafana release. Docker `grafana/grafana` pulls `latest`, which may not match the doc version. **Mitigation:** Pin the Docker tag to the version documented (check source_url). If the UI has changed, this is the exact scenario the product is meant to detect.

2. **Agent getting lost.** The `-p` agent may click wrong elements, trigger unexpected dialogs, or loop. **Mitigation:** Claude Code's built-in tool call limits bound the session. At MVP scale (17 screens), we can manually review every navigation log. If a `-p` call doesn't produce the expected output files, it's a failure — log and move on.

3. **chrome-devtools MCP tool coverage.** The MCP server may not expose all tools needed (e.g., hover, drag, scroll into view, handle dropdowns). **Mitigation:** Run a quick smoke test before starting: verify the MCP server can navigate, click, type, and screenshot on Grafana's login page. If specific tools are missing, check if `evaluate` (JS execution) can fill the gap.

4. **Browser state pollution between `-p` calls.** Relying on Chrome's persistent state means a failed navigation can leave the browser on an unexpected page, breaking subsequent plans. **Mitigation:** Before each root navigation path, the prompt instructs the agent to navigate to `localhost:3000` first (known starting state). For branch navigations, the prompt tells the agent what screen it should currently be on and to verify before proceeding.

5. **Text description quality.** If the agent's text description of the screen misses a UI element, Haiku can't verify it from text alone. **Mitigation:** The image fallback path catches this. Track the uncertain→fallback rate — if >50%, the description prompt needs improvement.

6. **Behavior claims need action sequences.** Claims like "Selecting 'Configure visualization' opens panel edit mode" require performing an action and observing the result. **Mitigation:** The driver plan specifies whether the agent should observe static state or perform an action. For action claims, the prompt instructs the agent to describe the state before and after.

### Open Questions
1. **Claim extraction prompt tuning.** How much iteration on the extraction prompt to match ground truth quality? Plan for 2-3 variants.

2. **chrome-devtools MCP server selection.** Need to identify the exact package — `chrome-devtools-mcp`, `@anthropic-ai/mcp-server-puppeteer`, or a community alternative. Evaluate which one exposes the tools we need (navigate, click, type, screenshot at minimum). Resolve before Step 0.

3. **`-p` output parsing.** The `-p` flag outputs the agent's final text response to stdout. We need the agent to write files (screenshots, descriptions) via tools AND produce a parseable status in stdout. Test the output format and build parsing accordingly.

4. **Scale path.** Once MVP validates, the next step is all 15 clean pages + mutated samples across all three products. Keycloak needs admin bootstrap, NetBox needs PostgreSQL + Redis. Plan in a follow-up.

5. **Agent prompting strategy.** Should the agent get the full page documentation for context, or only the navigation hints from the plan? Full context risks biasing it (it "knows" what to expect instead of discovering it). Plan-only tests autonomous navigation more honestly. **Recommendation:** start with plan-only, add doc context if navigation success rate is below 50%.

---

## File Structure (after implementation)

```
sandbox-demo-trial/
├── PLAN_mvp-pipeline.md       ← this file
├── pipeline/
│   ├── __init__.py
│   ├── config.py              # Docker config, Chrome port, model names, output paths
│   ├── models.py              # Pydantic: ExtractedClaim, DriverPlan, ScreenState, Verdict
│   ├── extract.py             # Phase 1: doc → claims (claude -p --model haiku)
│   ├── plan.py                # Phase 2: claims → driver plans (claude -p --model sonnet)
│   ├── drive.py               # Phase 3: autonomous navigation (claude -p + chrome-devtools MCP)
│   ├── verify.py              # Phase 4: claim + state → verdict (claude -p --model haiku)
│   ├── orchestrator.py        # End-to-end runner + reporting
│   └── prompts/
│       ├── extract_claims.txt
│       ├── plan_navigation.txt
│       ├── agent_system.txt   # Navigation agent prompt (for chrome-devtools -p calls)
│       └── verify_claim.txt
├── results/                   # Pipeline output (gitignored)
│   ├── claims/
│   ├── plans/
│   ├── screenshots/           # PNG per screen state
│   ├── descriptions/          # Text description per screen state
│   ├── navigation_logs/       # Raw -p stdout per screen (for debugging)
│   └── verdicts/
├── dataset/                   # Existing — ground truth
├── .claude/settings.json      # MCP server config + permissions
└── requirements.txt           # pydantic (only Python dep)
```

---

## Success Criteria for MVP

The MVP succeeds if:
1. **Claim extraction** achieves ≥80% recall against ground truth (≥20/25 claims matched)
2. **Autonomous navigation** reaches ≥70% of target screens (≥12/17 screens) — this is the key metric
3. **Verification on clean page** produces ≤2 false positives (≥92% specificity)
4. **Verification on mutated page** detects the M1 mutation (flags `grafana-p1-c1` as false)
5. **Total cost** stays under $5 for both runs combined (Phase 3 MCP driving is the dominant cost)

These thresholds are deliberately lenient — the point is validating the pipeline architecture, not achieving production accuracy. Navigation success rate (criterion 2) is the most important signal: if the agent can't reach screens autonomously, nothing downstream matters.

> **Wording corrected (2026-06-17, after the first run — see `PLAN_failure-remediation.md`).**
> The criteria above are only *measurable and meaningful* under these definitions, now
> enforced in code:
> - **All criteria require the deployed product version == the labeled version** (Fix 1).
>   The first run violated this (drove 11.6.0 against a 13.0 doc), which made criterion 3
>   meaningless — the "false positives" were mostly correct drift detections.
> - **Criteria 3/4 use one detection-framing confusion matrix** (`pipeline/metrics.py`):
>   FP = a *clean* claim flagged false; FN = a *missed contradiction* (the costly error per
>   MISSION.md); `uncertain` is a separate abstention bucket reported with `coverage`, and
>   is **never** folded into FP. (The first run's "10 FP" was really FP=10 *plus* 9 abstentions,
>   and an inverted evaluator had reported "19 FP".)
> - **Criterion 4 (M1)** must be detected *for the right reason* — a divergent navigation
>   **trace**, not a destination-only guess (Fix 2).
> - **Criterion 5** is now measurable: per-phase + total `cost_usd` in `results/pipeline_report.json`.
> - With only one labeled page live, all numbers are **DEV-only** until a TEST page exists (L4).

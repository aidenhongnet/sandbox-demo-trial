# Tools & Dependencies Landscape

> Detailed evaluation of every tool, framework, and dependency relevant to building an automated documentation quality checker. Organized by category with concrete adoption recommendations.

---

## 1. Computer-Use & Browser Automation Agents

### 1.1 Claude Computer Use (Anthropic)

**What it is:** API-native tool that lets Claude control full desktop environments via screenshots, clicks, typing, and scrolling.

**Key specs (June 2026):**
- Desktop-first (not browser-only) — controls native apps, terminal, file systems, and browsers
- OSWorld-Verified: Claude Opus 4.6 = 72.7%, Claude Sonnet 4.6 = 72.5%
- XGA resolution (1024x768) recommended for optimal accuracy
- "Zoom Action" feature (2026) for high-resolution inspection of small UI elements
- Cost: ~1,500-2,000 tokens per screenshot; typical task $0.50-$2.00
- Smart screenshot policies reduce costs 40-60%

**Why it matters for you:**
- Netwrix products are on-prem, often desktop-based — Claude CU can handle native Windows UIs, not just web
- Conservative execution model (asks before destructive actions) is a feature, not a bug, for doc verification
- Permission-aware defaults align well with a verification use case where you want *careful* interaction

**Limitations:**
- Slower than pure Playwright (each action involves "thinking" tokens)
- Cost scales with screenshot count
- Still ~27% failure rate on OSWorld benchmarks

**Integration path:** Use via the Anthropic API with `computer-20250124` tool type. Docker containers for sandboxed execution.

---

### 1.2 browser-use

**What it is:** Open-source Python library (MIT) that turns any LLM into a browser automation agent. 50K+ GitHub stars.

**Key specs:**
- Supports vision mode (screenshots) and DOM extraction mode (page structure), or both
- DOM-observation mode is 5-10x cheaper than screenshot mode
- Works with any LLM backend (Claude, GPT, Gemini, Ollama, etc.)
- Task completion: ~78% with Claude Opus on standardized tests
- Simple task (5 steps): $0.02-0.08

**Why it matters for you:**
- Open-source gives you full control over the automation pipeline
- Python ecosystem aligns with ML/AI tooling
- DOM mode is dramatically cheaper for pages where visual reasoning isn't needed
- Can switch between vision and DOM mode per-step

**Limitations:**
- Higher developer experience burden than vendor products
- DOM mode loses visual reasoning on rich interfaces (which you need for screenshot comparison)
- Browser-only (no native desktop app support)

**Integration path:** `pip install browser-use`, configure with your LLM provider.

---

### 1.3 Stagehand (Browserbase)

**What it is:** Open-source TypeScript SDK built on Playwright that adds AI primitives: `act()`, `extract()`, `observe()`. ~22.5K GitHub stars.

**Key specs:**
- Hybrid model: mix deterministic Playwright commands with AI-powered methods
- `act()`: $0.002-0.01 per call; `extract()`: $0.005-0.02 per call
- Stagehand 2.0 introduced `agent()` method for autonomous multi-step tasks
- 1-3 seconds per AI action (vs <100ms for pure Playwright)
- Maintenance: <5% adjustment rate vs 15-25% for pure Playwright selectors

**Why it matters for you:**
- Best of both worlds: deterministic speed for known paths + AI flexibility for visual reasoning
- Lower per-action cost than full autonomous agents
- "Act on what I describe" model maps well to doc instructions ("Click the Settings button")

**Limitations:**
- TypeScript only (though Go and Ruby ports exist)
- Limited multi-tab support
- Still tied to Browserbase infrastructure for cloud execution

**Integration path:** `npm install @browserbase/stagehand`, configure LLM provider.

---

### 1.4 Playwright (Raw)

**What it is:** Microsoft's browser automation framework. 70K+ GitHub stars. The industry standard.

**Key specs (v1.56+, 2025-2026):**
- Deterministic, no AI — every action is explicit
- Native AI agents added in v1.56: Planner, Generator, Healer
- AI Healer auto-repairs failed tests using MCP
- Visual comparison: `toHaveScreenshot()` with `maxDiffPixels` and `maxDiffPixelRatio`
- Cross-browser (Chromium, Firefox, WebKit)
- ~98% task completion on standardized tests (but 15-25% selector fix rate within 30 days)

**Why it matters for you:**
- Foundation layer for all browser-based testing
- MCP server exists for Claude Code integration
- Visual regression capabilities for screenshot comparison
- The new AI Healer reduces maintenance burden significantly

**Limitations:**
- Brittle without AI — selectors break with UI changes
- No semantic understanding of what's on screen
- Browser-only (no desktop app support)

**Recommendation:** Use Playwright as the deterministic backbone. Layer AI on top via Stagehand, browser-use, or Claude Computer Use for the reasoning layer.

---

### 1.5 LaVague

**What it is:** Open-source Python framework for web agents using Large Action Models. Built on Selenium/Playwright.

**Key specs:**
- LaVague QA: turns Gherkin specs into Pytest code
- Supports OpenAI, Llama, Gemini, Azure OpenAI
- Modular architecture (World Model + Action Engine + Driver)

**Why it matters for you:**
- Gherkin-to-test capability could be adapted for doc-to-test generation
- Less mature than browser-use but more structured architecture

**Limitations:**
- Smaller community and ecosystem
- Less battle-tested in production

---

### 1.6 UiPath Screen Agent

**What it is:** Enterprise RPA tool powered by Claude Opus 4.5 for AI-driven UI automation.

**Key specs:**
- OSWorld-Verified: 67.1% (was #1 at time of announcement, January 2026)
- Uses natural language to create UI automation
- Integrates with full UiPath RPA platform
- Handles desktop apps, not just web

**Why it matters for you:**
- Proves the Claude + desktop UI automation pattern works at enterprise scale
- UiPath's orchestration layer handles the "run on VM" problem

**Limitations:**
- Enterprise licensing costs
- Oriented toward RPA workflows, not documentation verification
- You'd be paying for a lot of RPA infrastructure you don't need

---

### 1.7 Manus AI

**What it is:** Autonomous general-purpose AI agent. Runs specialized agents in isolated Linux sandboxes.

**Key specs:**
- GAIA benchmark Level 3: ~57.7%
- Desktop app with "My Computer" feature (macOS/Windows)
- $100M ARR (Dec 2025), Meta acquisition blocked by China

**Why it matters for you:**
- Demonstrates what a fully autonomous agent can do
- Desktop app model is interesting for on-prem testing

**Limitations:**
- Geopolitical uncertainty
- Less controllable than API-based tools
- Not designed for documentation verification specifically

---

## 2. Documentation Testing & Quality

### 2.1 Doc Detective

**What it is:** Open-source documentation testing framework that executes docs as test specs.

**Key capabilities:**
- Parses Markdown, AsciiDoc, DITA
- Tests CLI commands, API calls, UI actions
- CI/CD pipeline integration
- MCP server at `https://docs.doc-detective.com/_mcp/server`
- Claude Code skill available
- VS Code extension available

**Why it matters for you:**
- **Most directly relevant tool.** It already does what you want for CLI/API docs.
- The "docs as tests" philosophy is your product's conceptual foundation
- MCP server means you can integrate it into an agent workflow

**Gap to fill:** Doc Detective's UI testing is basic. Your product needs to extend this with:
1. Visual/screenshot comparison (Doc Detective verifies text-based UI actions; you need to verify visual state)
2. Rich desktop app support (Doc Detective is web/CLI focused)
3. Semantic reasoning ("Does this screen match what the docs describe?" vs "Did this click succeed?")

**Integration path:** `npm install doc-detective`, or use MCP server for agent integration.

---

### 2.2 Vale

**What it is:** Open-source prose linter. Enforces style guides via configurable rules.

**Key capabilities:**
- Supports Markdown, reStructuredText, AsciiDoc, HTML
- Import Microsoft, Google, or custom style guides
- CI/CD integration via CLI
- Used by Elastic, Grafana, ING, Spectro Cloud

**Why it matters for you:**
- Addresses **quality drift** (terminology consistency, voice, wording)
- Cheap to run, easy to integrate
- Good complement to your contradiction checker (different layer of quality)

**Limitation:** Only checks prose quality, not factual accuracy against the product.

---

### 2.3 Docs as Tests (Methodology)

**What it is:** A framework treating documentation as executable test cases, developed by Manny Silva (book: *Docs as Tests: A Strategy for Resilient Technical Documentation*).

**Implementation levels:**
1. **Minimal:** Production testing per release
2. **Good:** Staging per push + production per release
3. **Better:** Add daily production testing for critical issues
4. **Optimal:** Add ad-hoc development testing with warning-only failures

**Key result:** Kong's AI chatbot accuracy improved from 84% to 91% after restructuring CLI guides using Docs as Tests.

**Why it matters for you:**
- Provides the methodology your product implements
- The development-staging-production pipeline maps to your versioned VM approach
- The "tests as warnings in dev, gates in staging" pattern is exactly right for your phased rollout

---

### 2.4 CI/CD Drift Detection Pattern

**What it is:** GitHub Actions workflow that uses Claude Code to detect doc drift at merge time (from understandingdata.com).

**Architecture:**
- Triggers on `pull_request: closed` events
- Extracts changed files via `git diff`
- Claude Code analyzes code-to-docs mapping
- Auto-creates follow-up PR with doc updates
- Cost: $0.50-$2.00 per run

**Key features:**
- Prompt injection mitigation with XML delimiter tags
- Author-association gating (only OWNER/MEMBER/COLLABORATOR)
- CLAUDE.md file structures project knowledge
- Code-to-docs mapping table

**Why it matters for you:**
- This is the *proactive* complement to your *reactive* checker
- The code-to-docs mapping table pattern is reusable
- The cost model proves this is economically viable at CI frequency

---

## 3. Visual Testing & Screenshot Management

### 3.1 Applitools Eyes

**What it is:** AI-powered visual testing platform. Most mature visual AI in the market.

**Key capabilities:**
- Visual AI distinguishes meaningful changes from noise
- Cross-browser, cross-device comparison
- Figma plugin + Storybook addon (Eyes 10.22, Jan 2026)
- Ignores anti-aliasing, font rendering differences

**Why it matters for you:**
- Best tool for comparing doc screenshots with actual product screenshots
- AI-based comparison reduces false positives from minor rendering differences
- Could be part of your "visual assertion" pipeline

---

### 3.2 Percy (BrowserStack)

**Key differentiator:** Visual Review Agent (late 2025) uses AI to classify visual diffs as meaningful or noise. 5,000 free screenshots/month.

**Why it matters for you:** Cross-browser comparison for web UIs. Less relevant for desktop apps.

---

### 3.3 shot-scraper + Kong Pattern

**What it is:** Open-source tool for automated screenshots. Kong uses it with macros (JavaScript functions executed before capture) to:
- Remove unreleased features from screenshots
- Inject sample data
- Add numbered annotation callouts
- Configure dashboards before capture

**Why it matters for you:**
- The "capture with pre-configured state" pattern is exactly what you need for generating "actual" screenshots
- Scripts are version-controlled and reproducible
- Can be combined with your VM provisioning layer

---

### 3.4 DocsHound

**What it is:** AI-powered screenshot documentation tool. Chrome extension captures demos and uses visual AI for element detection.

**Why it matters for you:** The "visual AI identifies UI elements" capability is relevant, but DocsHound is focused on *creating* docs, not *verifying* them.

---

### 3.5 Ferndesk

**What it is:** Documentation platform that captures/annotates screenshots and detects when product UI changes.

**Why it matters for you:** The "detect when UI changes affect docs" feature is directly relevant. Worth evaluating whether their detection engine could be integrated or whether their approach should be replicated.

---

## 4. Agent Orchestration & Multi-Agent Frameworks

### 4.1 Multi-Agent Review Pattern (BuildArena-style)

Five roles: **Planner** (decomposes doc pages into test scenarios) -> **Drafter** (generates test assertions) -> **Reviewer** (cross-checks against product) -> **Builder** (executes tests) -> **Guidance** (encodes doc quality standards).

This pattern directly maps to your documentation checker workflow.

### 4.2 MCP (Model Context Protocol)

**Why it's the integration layer:**
- Doc Detective has an MCP server
- Playwright has MCP servers
- Claude Code natively supports MCP
- Your doc checker can be exposed as an MCP tool
- Tools compose via MCP without custom integration code

### 4.3 Agent Browser CLI

**What it is:** Rust-based tool that provides a "snapshot-and-ref" model for AI browser interaction.

**Key innovation:** Interactive elements get `@e1`, `@e2` refs. AI reads accessibility tree and decides which element to interact with. Eliminates selector maintenance entirely.

**Integration:** Used with Claude Code for automated QA. Outputs structured JSON with verdicts (HEALTHY/MINOR_ISSUES/CRITICAL_BUGS).

---

## 5. Dependency Recommendation Summary

### Must-Have (Core Stack)

| Dependency | Role | License |
|-----------|------|---------|
| **Playwright** | Browser automation backbone | Apache 2.0 |
| **Claude Computer Use API** | Visual reasoning + desktop control | Commercial API |
| **Doc Detective** | Doc parsing + test execution framework | MIT |
| **Vale** | Prose quality linting | MIT |

### Should-Have (Quality Layer)

| Dependency | Role | License |
|-----------|------|---------|
| **browser-use** OR **Stagehand** | AI-augmented browser automation | MIT |
| **Applitools Eyes** OR **Percy** | Visual regression comparison | Commercial |
| **shot-scraper** | Automated screenshot capture | Apache 2.0 |

### Nice-to-Have (Orchestration)

| Dependency | Role | License |
|-----------|------|---------|
| **MCP servers** (Playwright, Doc Detective) | Agent tool integration | Various |
| **Agent Browser CLI** | Selector-free browser interaction | MIT |
| **GitHub Actions** | CI/CD automation | N/A |

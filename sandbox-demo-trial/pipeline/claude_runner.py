from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Cost ledger — every `claude -p` call records its total_cost_usd here so the
# orchestrator can report per-phase + total cost (success criterion 5). The
# orchestrator brackets each phase with mark()/since(); the ledger accumulates
# globally and the deltas are per-phase.
# ---------------------------------------------------------------------------

@dataclass
class _CostEntry:
    model: str
    cost_usd: float
    usage: dict | None = None


@dataclass
class CostLedger:
    _entries: list[_CostEntry] = field(default_factory=list)

    def record(self, model: str, cost_usd: float | None, usage: dict | None = None) -> None:
        if cost_usd is None:
            return
        self._entries.append(_CostEntry(model, float(cost_usd), usage))

    def mark(self) -> int:
        """Return a snapshot marker for since()."""
        return len(self._entries)

    def since(self, mark: int) -> float:
        return sum(e.cost_usd for e in self._entries[mark:])

    @property
    def total(self) -> float:
        return sum(e.cost_usd for e in self._entries)

    def estimated_total(self) -> float:
        """Rate-card estimate from token usage, for cross-checking `total`."""
        from . import metrics  # deferred to avoid any load-time cycle

        return sum(metrics.estimate_cost(e.model, e.usage) or 0.0 for e in self._entries)

    def reset(self) -> None:
        self._entries.clear()


COST = CostLedger()


def _extract_json_from_text(text: str) -> Any | None:
    """Extract JSON from text that may contain markdown code fences."""
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _invoke_cli(cmd: list[str], prompt: str, timeout: int) -> subprocess.CompletedProcess:
    """Run `cmd` feeding `prompt` on stdin via a temp file (Windows-safe)."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write(prompt)
        prompt_path = Path(f.name)
    try:
        with open(prompt_path, encoding="utf-8") as stdin_f:
            return subprocess.run(
                cmd,
                stdin=stdin_f,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
    finally:
        prompt_path.unlink(missing_ok=True)


def _invoke_cli_retry(
    cmd: list[str], prompt: str, timeout: int, *, retries: int = 2, backoff: float = 4.0
) -> subprocess.CompletedProcess:
    """Invoke the CLI, retrying transient non-zero exits / timeouts.

    `claude -p` occasionally exits non-zero on a transient API/rate-limit blip; a
    single such blip should not be fatal to a multi-call phase (the first live run
    lost a 2-hour drive when one plan call exited 1). Retries the same call up to
    `retries` times with linear backoff. The final attempt's result is returned
    (or TimeoutExpired re-raised) for the caller to handle exactly as before.
    """
    last: subprocess.CompletedProcess | None = None
    for attempt in range(retries + 1):
        try:
            cp = _invoke_cli(cmd, prompt, timeout)
        except subprocess.TimeoutExpired:
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
                continue
            raise
        if cp.returncode == 0:
            return cp
        last = cp
        if attempt < retries:
            time.sleep(backoff * (attempt + 1))
    assert last is not None
    return last


def run_claude(
    prompt: str,
    *,
    model: str,
    json_output: bool = False,
    allowed_tools: str | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    """Shell out to `claude -p` and return parsed output.

    Returns a dict with keys: success, raw, and (when json_output) parsed.
    Cost/usage are captured for every call via the `--output-format json`
    envelope (whose `result` field holds the model's text response) and recorded
    to the module-level COST ledger. `raw` is always the unwrapped response text,
    so callers that don't need JSON (drive, pre-auth) see the same text as before
    while still contributing their cost.
    """
    # Always request the JSON envelope so total_cost_usd is available even when
    # the caller only wants the raw text. The model loop is identical regardless
    # of output format.
    cmd = ["claude", "-p", "--model", model, "--output-format", "json"]
    if allowed_tools:
        cmd += ["--allowedTools", allowed_tools]

    try:
        result = _invoke_cli_retry(cmd, prompt, timeout)
    except subprocess.TimeoutExpired:
        return {"success": False, "raw": "", "error": f"Timed out after {timeout}s"}

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    if result.returncode != 0:
        return {"success": False, "raw": stdout, "error": stderr or f"Exit code {result.returncode}"}

    response: dict[str, Any] = {"success": True, "raw": stdout}
    if not stdout:
        return response

    try:
        wrapper = json.loads(stdout)
    except json.JSONDecodeError:
        # No envelope (unexpected with --output-format json): keep raw stdout.
        if json_output:
            response["parsed"] = None
            response["parse_error"] = "Failed to parse JSON envelope from stdout"
        return response

    if isinstance(wrapper, dict) and "result" in wrapper:
        COST.record(model, wrapper.get("total_cost_usd"), wrapper.get("usage"))
        response["cost_usd"] = wrapper.get("total_cost_usd")
        response["usage"] = wrapper.get("usage")
        response["duration_ms"] = wrapper.get("duration_ms")
        response["session_id"] = wrapper.get("session_id")

        model_text = wrapper["result"]
        if isinstance(model_text, str):
            response["raw"] = model_text
            if json_output:
                parsed = _extract_json_from_text(model_text)
                response["parsed"] = parsed
                if parsed is None:
                    response["parse_error"] = "Model response is not valid JSON"
        else:
            response["raw"] = json.dumps(model_text)
            if json_output:
                response["parsed"] = model_text
    else:
        # Envelope without a `result` field — surface it directly.
        if json_output:
            response["parsed"] = wrapper

    return response


def run_claude_stream(
    prompt: str,
    *,
    model: str,
    allowed_tools: str | None = None,
    timeout: int = 600,
) -> dict[str, Any]:
    """Run `claude -p` with `--output-format stream-json` to capture the tool-call
    event stream (Fix 2 — the navigation action trace, not just the destination).

    Returns dict with: success, raw (final result text), events (parsed ndjson),
    cost_usd, usage. Cost is recorded to COST like every other call.

    DRIVER smoke test: confirm this CLI version emits `tool_use` events for the
    chrome-devtools MCP tools. If it does not, `events` comes back without tool
    calls and `parse_mcp_trace` yields an empty trace — callers then fall back to
    the agent-authored trace file (see drive.py), so no silent degradation.
    """
    cmd = ["claude", "-p", "--model", model,
           "--output-format", "stream-json", "--verbose"]
    if allowed_tools:
        cmd += ["--allowedTools", allowed_tools]

    try:
        result = _invoke_cli_retry(cmd, prompt, timeout)
    except subprocess.TimeoutExpired:
        return {"success": False, "raw": "", "events": [], "error": f"Timed out after {timeout}s"}

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if result.returncode != 0:
        return {"success": False, "raw": stdout, "events": [],
                "error": stderr or f"Exit code {result.returncode}"}

    events: list[dict] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # tolerate any non-JSON noise lines

    raw, cost, usage = "", None, None
    for ev in events:
        if isinstance(ev, dict) and ev.get("type") == "result":
            res = ev.get("result")
            raw = res if isinstance(res, str) else raw
            cost = ev.get("total_cost_usd", cost)
            usage = ev.get("usage", usage)
    COST.record(model, cost, usage)

    return {"success": True, "raw": raw, "events": events,
            "cost_usd": cost, "usage": usage}


def parse_mcp_trace(events: list[dict]) -> list[dict]:
    """Extract chrome-devtools MCP tool calls from stream-json events into an
    ordered action trace (best-effort). The agent-authored trace is the richer,
    authoritative source for resulting URL/title; this is the tamper-proof
    corroboration of the action *sequence*.
    """
    steps: list[dict] = []
    for ev in events:
        if not isinstance(ev, dict) or ev.get("type") != "assistant":
            continue
        content = (ev.get("message") or {}).get("content") or []
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name", "")
            if "chrome-devtools" not in name and "chrome_devtools" not in name:
                continue
            inp = block.get("input") or {}
            target = (
                inp.get("uid") or inp.get("selector") or inp.get("text")
                or inp.get("url") or ""
            )
            steps.append({
                "step": len(steps) + 1,
                "action": name.split("__")[-1] if "__" in name else name,
                "target_label": str(target),
                "raw_input": inp,
            })
    return steps

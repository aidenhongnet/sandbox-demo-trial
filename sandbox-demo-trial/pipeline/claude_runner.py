from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


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


def run_claude(
    prompt: str,
    *,
    model: str,
    json_output: bool = False,
    allowed_tools: str | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    """Shell out to `claude -p` and return parsed output.

    Returns dict with keys: success, raw, parsed (if json_output).
    When json_output=True, `--output-format json` produces a wrapper
    object with a `result` field containing the model's text response.
    We unwrap that and parse any JSON the model returned.
    """
    cmd = ["claude", "-p", "--model", model]
    if json_output:
        cmd += ["--output-format", "json"]
    if allowed_tools:
        cmd += ["--allowedTools", allowed_tools]

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write(prompt)
        prompt_path = Path(f.name)

    try:
        result = subprocess.run(
            cmd,
            stdin=open(prompt_path, encoding="utf-8"),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "raw": "", "error": f"Timed out after {timeout}s"}
    finally:
        prompt_path.unlink(missing_ok=True)

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()

    if result.returncode != 0:
        return {"success": False, "raw": stdout, "error": stderr or f"Exit code {result.returncode}"}

    response: dict[str, Any] = {"success": True, "raw": stdout}

    if json_output and stdout:
        try:
            wrapper = json.loads(stdout)
        except json.JSONDecodeError:
            response["parsed"] = None
            response["parse_error"] = "Failed to parse JSON from stdout"
            return response

        if isinstance(wrapper, dict) and "result" in wrapper:
            response["cost_usd"] = wrapper.get("total_cost_usd")
            response["usage"] = wrapper.get("usage")
            response["duration_ms"] = wrapper.get("duration_ms")
            response["session_id"] = wrapper.get("session_id")
            model_text = wrapper["result"]
            if isinstance(model_text, str):
                parsed = _extract_json_from_text(model_text)
                response["parsed"] = parsed
                response["raw"] = model_text
                if parsed is None:
                    response["parse_error"] = "Model response is not valid JSON"
            else:
                response["parsed"] = model_text
        else:
            response["parsed"] = wrapper

    return response

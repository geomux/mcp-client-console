# salvage.py
# Rescues tool calls that the model wrote as plain text instead of actually calling.
# Small models sometimes narrate {"name": "run_command", ...} in their reply - the
# call never happens and the loop stalls. This module finds those, validates them
# against the real tool list, and converts them into genuine ToolCall objects.

import json
from mcp_client_console.llm.provider_base import ToolCall

MAX_SALVAGED_CALLS = 3


### ---------------------------
### --- JSON OBJECT SCANNER ---
### ---------------------------

def _json_candidates(text: str):
    """Yield balanced top-level {...} spans found anywhere in the text.
    text: the model's plain-text reply (code fences are just text and scan fine).
    """
    depth = 0
    start = None
    in_string = False
    escaped = False
    for position, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = position
            depth += 1
        elif char == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    yield text[start:position + 1]
                    start = None


### -------------------------
### --- SHAPE RECOGNIZERS ---
### -------------------------

def _extract_shape(candidate: dict) -> tuple[str, dict] | None:
    """Pull (tool_name, arguments) out of the known tool-call JSON shapes, or None.
    candidate: a parsed JSON object.
    Accepted shapes: {"name": t, "arguments": {...}}, {"tool": t, "args": {...}},
    {"name": t, "parameters": {...}}, {"function": {"name": t, "arguments": {...}}}.
    """
    if not isinstance(candidate, dict):
        return None
    scope = candidate
    inner = candidate.get("function")
    if isinstance(inner, dict):
        scope = inner
    name = scope.get("name") or scope.get("tool")
    if not isinstance(name, str) or not name:
        return None
    for key in ("arguments", "args", "parameters", "input"):
        value = scope.get(key)
        if isinstance(value, dict):
            return name, value
    return None


### --------------------
### --- PUBLIC ENTRY ---
### --------------------

def extract(text: str, tool_names: set[str]) -> list[ToolCall]:
    """Find real, validated tool calls written as text; return them as ToolCall objects.
    text: the model's plain-text reply.
    tool_names: the set of tools that actually exist on the server.
    Only exact known tool names with dict arguments are accepted; duplicates are
    dropped; at most MAX_SALVAGED_CALLS are returned.
    """
    if not text or "{" not in text or not tool_names:
        return []
    calls = []
    seen = set()
    for span in _json_candidates(text):
        try:
            parsed = json.loads(span)
        except json.JSONDecodeError:
            continue
        shape = _extract_shape(parsed)
        if shape is None:
            continue
        name, arguments = shape
        if name not in tool_names:
            continue
        key = (name, json.dumps(arguments, sort_keys=True, default=str))
        if key in seen:
            continue
        seen.add(key)
        calls.append(ToolCall(call_id=f"salvaged_{len(calls)}_{name}", name=name, arguments=arguments))
        if len(calls) >= MAX_SALVAGED_CALLS:
            break
    return calls

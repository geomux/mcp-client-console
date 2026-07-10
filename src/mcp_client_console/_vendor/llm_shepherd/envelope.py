# envelope.py
# Rewrites raw tool results into receipts a small model cannot misread.
# The #1 loop trigger is an ambiguous or empty result - the envelope makes every
# result explicit: numbered, status-labeled, never blank, and marked FINAL.

import re


### -----------------------
### --- STATUS CLASSIFY ---
### -----------------------

_EXIT_CODE_PATTERN = re.compile(r"\[exit code (\d+)\]")

EMPTY_BODY_TEXT = (
    "(empty output - the tool ran fine but returned nothing. "
    "For a search or listing this means: NO MATCHES. For a file read: the file is empty. "
    "This is a real answer, not an error.)"
)


def classify(raw: str) -> tuple[str, str, str | None]:
    """Classify a raw result into (coarse, display, extra_line).
    raw: raw tool result text.
    coarse: OK | DENIED | ERROR | USER_DENIED (for ledger bookkeeping).
    display: status text shown in the receipt header (may include exit code).
    extra_line: optional plain-language line explaining the status.
    """
    stripped = raw.strip()
    if stripped.startswith("DENIED"):
        return "DENIED", "DENIED", "This is a policy denial. Retrying the same thing cannot succeed."
    if stripped.startswith("ERROR"):
        return "ERROR", "ERROR", None
    if "denied by user" in stripped.lower():
        return "USER_DENIED", "DENIED BY USER", "The user declined tool access. Answer in chat only - never pretend a tool ran."
    exit_match = _EXIT_CODE_PATTERN.search(stripped)
    if exit_match:
        code = exit_match.group(1)
        return "OK", f"OK (exit {code})", (
            f"NOTE: exit code {code} is nonzero - the command itself reported a problem. "
            "Read its message above instead of re-running the identical command."
        )
    return "OK", "OK", None


### ------------------
### --- TRUNCATION ---
### ------------------

def truncate(text: str, limit: int) -> str:
    """Cut oversized text to limit chars, keeping the head and tail.
    text: the body to bound.
    limit: maximum characters allowed.
    Protects the model's context window - an overflowing window silently evicts
    history and is a major cause of 'model forgot what it already did' loops.
    """
    if limit <= 0 or len(text) <= limit:
        return text
    head = int(limit * 0.75)
    tail = max(1, int(limit * 0.15))
    omitted = len(text) - head - tail
    return (
        text[:head]
        + f"\n[... {omitted} characters omitted to protect the context window ...]\n"
        + text[-tail:]
    )


### ---------------------
### --- RESULT WRAPPER ---
### ---------------------

def wrap(step_index: int, tool_name: str, raw: str, max_chars: int, notes: list[str] | None = None) -> str:
    """Build the final receipt string delivered to the model.
    step_index: 1-based step number within the episode.
    tool_name: which tool produced this result.
    raw: raw result text.
    max_chars: truncation limit for the body.
    notes: optional extra coaching lines appended after the receipt footer.
    """
    _coarse, display, extra = classify(raw)
    body = raw if raw.strip() else EMPTY_BODY_TEXT
    body = truncate(body, max_chars)
    lines = [f"[TOOL RESULT #{step_index} | {tool_name} | {display}]", body]
    if extra:
        lines.append(extra)
    lines.append(
        f"[result #{step_index} is complete and FINAL - running the identical call again returns this same result]"
    )
    for note in notes or []:
        if note:
            lines.append(note)
    return "\n".join(lines)

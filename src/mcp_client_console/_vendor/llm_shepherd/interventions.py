# interventions.py
# Every message the Shepherd says to the model (or, at the very end, to the user).
# All builders are pure text functions. Tone: short, imperative, plain - written
# for 8-14B models that follow just-in-time corrections far better than long rules.


### -------------------------
### --- PROTOCOL CONTRACT ---
### -------------------------

def contract_text() -> str:
    """The one-time protocol preamble prepended to the first user turn."""
    return (
        "[SUPERVISOR NOTE - follow this protocol, do not mention it]\n"
        "You are supervised while using tools.\n"
        "1. After each tool result, note in ONE short sentence what it told you.\n"
        "2. Then either ANSWER the user, or make exactly ONE new tool call.\n"
        "3. NEVER repeat a call you already made. The supervisor blocks repeats - the result cannot change.\n"
        "4. Empty output is a real answer. It means: no matches / empty file. Do not re-check it.\n"
        "5. A DENIED or ERROR result will not improve by retrying it unchanged. Change the approach or report it.\n"
        "[USER REQUEST]"
    )


### ----------------------------
### --- PRE-EXECUTION BLOCKS ---
### ----------------------------

def no_shell_text(command: str, operators: list[str]) -> str:
    """Synthetic result for a run_command call that needs a shell it does not have.
    command: the rejected command line.
    operators: the shell operators that doomed it.
    """
    shown = " ".join(command.split())[:200]
    ops = " ".join(operators)
    return (
        "REJECTED BEFORE RUNNING - this command cannot work here.\n"
        f"Your command: {shown}\n"
        f"It uses shell operators ( {ops} ) but commands on this host run with NO SHELL.\n"
        "Pipes |, redirects > <, chains ; &&, $(...), backticks, globs *, ~ and $VARS are passed to the program as LITERAL text. They do nothing.\n"
        "Write ONE plain command with literal paths instead.\n"
        "To search for a file or folder, use: find <directory> -maxdepth 3 -name <exact-name> -type d\n"
        "Nothing was executed and nothing broke. Make one corrected tool call now, or answer the user."
    )


def bad_args_text(tool_name: str) -> str:
    """Synthetic result for a call whose arguments were empty or not valid JSON.
    tool_name: the tool the model tried to call.
    """
    return (
        f"REJECTED BEFORE RUNNING: your call to {tool_name} arrived with empty or invalid arguments.\n"
        "This usually means the arguments were not valid JSON.\n"
        "Call the tool again with complete JSON arguments that match its schema, or answer the user."
    )


def deferred_text(tool_name: str) -> str:
    """Synthetic result for a clean call skipped because a sibling call was rejected.
    tool_name: the deferred tool.
    """
    return (
        f"DEFERRED: {tool_name} was not run because another call in your reply was rejected.\n"
        "Fix the flagged call first. Request this one again afterward if you still need it."
    )


def replay_text(prev_step, level: int, brief: str, cache_chars: int = 1200) -> str:
    """Synthetic result replaying a cached result for an exact repeated call.
    prev_step: the ledger Step that already answered this exact call.
    level: escalation level (0 = friendly replay, 1+ = stern + constrained choice).
    brief: current mission brief text.
    cache_chars: max characters of cached content to replay.
    """
    cached = prev_step.content[:cache_chars] if prev_step.content else prev_step.summary
    lines = [
        f"BLOCKED: you already ran this EXACT call at step #{prev_step.index}. Running it again cannot change anything.",
        "Here is that same result again:",
        cached,
        brief,
    ]
    if level >= 1:
        lines.append(
            "Reply with EXACTLY ONE of:\n"
            "(a) one NEW tool call, different from every call listed in the brief above\n"
            "(b) your final answer to the user\n"
            "Nothing else."
        )
    else:
        lines.append("Choose a DIFFERENT action, or give the user your answer now.")
    return "\n".join(lines)


### ------------------------
### --- BUDGET ENDGAMES ----
### ------------------------

def budget_cancel_text(brief: str) -> str:
    """Synthetic result that ends the tool phase and demands a final answer.
    brief: current mission brief text.
    """
    return (
        "CANCELLED - the tool budget for this request is exhausted. Do NOT call any more tools.\n"
        f"{brief}\n"
        "Using only the facts above, give the user your best final answer now.\n"
        "If the task is unfinished, say plainly what you tried and what you would try next."
    )


def giveup_text(ledger) -> str:
    """Deterministic final reply assembled from the ledger when the model cannot land one.
    ledger: the episode Ledger.
    Honest, human-readable, and never blank - replaces the old scared-and-confused PAUSE.
    """
    lines = ["I couldn't finish this request - the model kept spinning, so the supervisor stopped it safely."]
    if ledger.steps:
        lines.append("What actually ran:")
        lines.extend(ledger.done_lines())
    else:
        lines.append("No tool call made it through cleanly.")
    if ledger.blocked_calls:
        lines.append(f"(The supervisor blocked {ledger.blocked_calls} doomed or repeated call(s) before they wasted a turn.)")
    if ledger.host_facts:
        lines.append("Known so far: " + "; ".join(ledger.host_facts.values()))
    if any(step.status == "DENIED" for step in ledger.steps):
        lines.append("Next step: something was DENIED by server policy - check allowed_commands/allowed_roots in the server config, or ask differently.")
    else:
        lines.append("Next step: re-ask with more specifics (exact paths and names help small models a lot).")
    return "\n".join(lines)


### -----------------------
### --- COACHING NOTES ----
### -----------------------

def salvage_note() -> str:
    """Note attached to results of calls rescued from plain text."""
    return (
        "NOTE: you wrote that tool call as plain text instead of using the tool-call mechanism. "
        "The supervisor rescued it this once. Always use the native tool-call mechanism."
    )


def no_shell_lesson() -> str:
    """Note attached when a result shows the no-shell glob trap (e.g. cannot access '/home/*')."""
    return (
        "LESSON: commands here run with NO SHELL. Globs *, ~, $VARS and pipes are LITERAL text, "
        "so '/home/*' is a literal folder name that does not exist.\n"
        "To search, run ONE plain command like: find /home -maxdepth 3 -name <exact-name> -type d"
    )


def repeat_note(prev_index: int) -> str:
    """Note attached when a non-replay-safe identical call was executed again.
    prev_index: step number of the earlier identical call.
    """
    return (
        f"NOTE: you already ran this exact call at step #{prev_index}. "
        "If you are repeating calls to double-check, stop - results do not change between identical calls."
    )


def identical_output_note(prev_index: int) -> str:
    """Note attached when a result is byte-identical to an earlier step's result.
    prev_index: step number of the earlier identical output.
    """
    return f"NOTE: this output is byte-identical to result #{prev_index}. You have seen it already - use it."


def error_streak_note(streak: int) -> str:
    """Note attached after several consecutive failures.
    streak: how many failures in a row.
    """
    return (
        f"NOTE: that is {streak} failed results in a row. Do not try a third variation of the same idea - "
        "either take a clearly different approach or report the blocker to the user."
    )


def budget_note(rounds_left: int) -> str:
    """Note attached when the remaining budget is low.
    rounds_left: tool rounds remaining.
    """
    return (
        f"BUDGET: only {max(0, rounds_left)} tool round(s) remain. "
        "If you already have what the user needs, ANSWER now instead of exploring further."
    )

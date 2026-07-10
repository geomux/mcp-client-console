# ledger.py
# The Shepherd's memory: what was asked, what ran, what came back, what's left in budget.
# Small models forget or distrust their own history - the ledger re-states it for them
# in a compact MISSION BRIEF so the truth survives context pressure.

import hashlib
import json
from dataclasses import dataclass


### -----------------------
### --- NORMALIZATION -----
### -----------------------

def normalize_args(arguments: dict) -> str:
    """Canonical one-line string for a tool call's arguments dictionary.
    arguments: the tool call arguments as a dict.
    Key order is sorted and command strings get their whitespace collapsed, so
    two calls that differ only in spacing/ordering still count as the same call.
    """
    if not isinstance(arguments, dict):
        return repr(arguments)
    cleaned = {}
    for key, value in arguments.items():
        if key == "command" and isinstance(value, str):
            value = " ".join(value.split())
        cleaned[key] = value
    try:
        return json.dumps(cleaned, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return repr(sorted(cleaned.items(), key=lambda item: str(item[0])))


def digest_of(content: str) -> str:
    """Short stable fingerprint of a result body (sha1, first 8 hex chars).
    content: raw result text.
    """
    return hashlib.sha1(content.encode("utf-8", "replace")).hexdigest()[:8]


def one_line(text: str, limit: int = 90) -> str:
    """First non-blank line of text, whitespace-collapsed and truncated.
    text: any result or argument text.
    limit: maximum characters kept.
    """
    for line in text.splitlines():
        squeezed = " ".join(line.split())
        if squeezed:
            return squeezed[:limit]
    return "(empty)"


### -------------------
### --- STEP RECORD ---
### -------------------

@dataclass
class Step:
    """One EXECUTED tool call and its result (synthetic coaching is never a Step).
    index: 1-based position within the episode.
    tool: tool name that ran.
    args_norm: canonical argument string from normalize_args().
    digest: fingerprint of the raw result, for spotting identical outputs.
    status: coarse result class - OK | DENIED | ERROR | USER_DENIED.
    summary: single trimmed line describing the result.
    content: raw result text (truncated) kept so repeats can be answered from cache.
    """
    index: int
    tool: str
    args_norm: str
    digest: str
    status: str
    summary: str
    content: str = ""


### --------------------
### --- LEDGER CLASS ---
### --------------------

class Ledger:
    """Tracks one episode (one user request) plus a few facts that persist across episodes."""

    def __init__(self):
        self.host_facts: dict[str, str] = {}  # survives across episodes (e.g. path style)
        self.episodes = 0
        self._reset_episode("")

    def _reset_episode(self, goal: str):
        """Wipe per-episode state for a fresh user request.
        goal: the user's request text.
        """
        self.goal = goal
        self.steps: list[Step] = []
        self.pending: dict[str, tuple[str, str]] = {}  # call_id -> (tool, args_norm)
        self.total_rounds = 0          # every model round trip, real or synthetic
        self.visible_batches = 0       # tool batches actually handed to the Orchestrator
        self.interventions_used = 0    # synthetic correction rounds spent
        self.blocked_calls = 0         # calls stopped before execution
        self.salvage_count = 0         # tool calls rescued out of plain text

    ### ------------------------
    ### --- EPISODE TRACKING ---
    ### ------------------------

    def begin_episode(self, goal: str):
        """Start tracking a new user request.
        goal: the user's request text.
        """
        self.episodes += 1
        self._reset_episode(goal)

    def register_pending(self, calls):
        """Remember the batch of calls just handed to the Orchestrator for execution.
        calls: list of ToolCall objects from the model's reply.
        """
        self.pending = {}
        for call in calls:
            self.pending[call.call_id] = (call.name, normalize_args(call.arguments))

    def record_result(self, call_id: str, tool: str, raw: str, status: str, keep_chars: int) -> Step:
        """Record one executed tool result as a Step and return it.
        call_id: linking id from the original ToolCall.
        tool: tool name.
        raw: raw result text.
        status: coarse status from envelope.classify().
        keep_chars: how much raw content to cache for replays.
        """
        pending = self.pending.pop(call_id, None)
        args_norm = pending[1] if pending else "(unknown args)"
        step = Step(
            index=len(self.steps) + 1,
            tool=tool,
            args_norm=args_norm,
            digest=digest_of(raw),
            status=status,
            summary=one_line(raw),
            content=raw[:keep_chars],
        )
        self.steps.append(step)
        self._learn_host_facts(raw)
        return step

    ### ----------------------
    ### --- LEDGER QUERIES ---
    ### ----------------------

    def find_exact(self, tool: str, args_norm: str) -> Step | None:
        """Most recent executed Step matching this exact call, or None.
        tool: tool name of the new call.
        args_norm: canonical arguments of the new call.
        """
        for step in reversed(self.steps):
            if step.tool == tool and step.args_norm == args_norm:
                return step
        return None

    def find_same_digest(self, digest: str, before_index: int) -> Step | None:
        """Earlier Step whose result was byte-identical, or None.
        digest: fingerprint of the newest result.
        before_index: only consider steps before this index.
        """
        for step in self.steps:
            if step.index < before_index and step.digest == digest:
                return step
        return None

    def error_streak(self) -> int:
        """Number of consecutive most-recent steps that failed (ERROR/DENIED/USER_DENIED)."""
        streak = 0
        for step in reversed(self.steps):
            if step.status in ("ERROR", "DENIED", "USER_DENIED"):
                streak += 1
            else:
                break
        return streak

    def _learn_host_facts(self, raw: str):
        """Harvest durable facts about the host from result text.
        raw: raw result text.
        """
        if "paths" not in self.host_facts:
            if any(marker in raw for marker in ("/home/", "/usr/", "/etc/", "/var/", "/opt/")):
                self.host_facts["paths"] = "host paths look POSIX (e.g. /home/...)"
            elif "\\" in raw and ":" in raw and any(f"{d}:\\" in raw for d in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
                self.host_facts["paths"] = "host paths look Windows (e.g. C:\\...)"

    ### ---------------------
    ### --- BRIEF RENDERS ---
    ### ---------------------

    def done_lines(self) -> list[str]:
        """One compact line per executed step, each capped near 120 chars."""
        lines = []
        for step in self.steps:
            args_view = step.args_norm[:60]
            line = f"  #{step.index} {step.tool} {args_view} -> {step.status}: {step.summary}"
            lines.append(line[:120])
        return lines

    def brief(self, rounds_left: int | None = None) -> str:
        """Render the MISSION BRIEF block injected back to the model.
        rounds_left: remaining tool-round budget to display (omit line when None).
        """
        lines = ["[MISSION BRIEF]"]
        goal_view = " ".join(self.goal.split())[:200]
        lines.append(f"GOAL: {goal_view}")
        if self.steps:
            lines.append("DONE SO FAR (final results - repeating any of these returns the same thing):")
            lines.extend(self.done_lines())
        if self.host_facts:
            lines.append("KNOWN HOST FACTS: " + "; ".join(self.host_facts.values()))
        if rounds_left is not None:
            lines.append(f"BUDGET: {max(0, rounds_left)} tool rounds left.")
        lines.append("RULES: never repeat a call listed above. Empty output is a real answer meaning no matches / empty file.")
        return "\n".join(lines)

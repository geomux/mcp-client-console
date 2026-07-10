# policy.py
# Tunable knobs for the Shepherd supervisor, with safe defaults that need zero config.
# Reads optional overrides from the user's config.toml [llm.shepherd] table.

from dataclasses import dataclass, fields


### -----------------------------
### --- DEFAULT COMMAND LISTS ---
### -----------------------------

# run_command binaries that are safe to answer from cache when the model repeats
# an identical call (read-only commands: same call, same machine, same answer).
READ_ONLY_COMMANDS = (
    "ls", "cat", "head", "tail", "find", "grep", "pwd", "whoami", "uname",
    "date", "wc", "stat", "which", "echo", "du", "df", "ps", "env", "id",
    "hostname", "file", "tree",
)


### --------------------
### --- POLICY CLASS ---
### --------------------

@dataclass
class Policy:
    """Every behavior knob the Shepherd supervisor honors.
    enabled: master switch - when False, attach() leaves the provider untouched.
    contract: inject the short agent-protocol preamble on the first user turn.
    brief_every: append a mission-brief refresh to every Nth tool result.
    max_result_chars: truncate any single tool result to this many characters.
    max_interventions_per_reply: cap on back-to-back corrections for one model reply.
    max_interventions_per_episode: cap on total corrections per user request.
    max_total_rounds: cap on ALL model round trips per user request (real + synthetic).
    visible_batch_limit: cap on tool batches shown to the Orchestrator (set by attach()
        to orchestrator.max_steps - 1 so the Shepherd always acts before the PAUSE).
    salvage: rescue tool calls the model wrote as plain text instead of calling them.
    preflight_shell_check: reject run_command calls using shell operators before they run.
    replayable_tools: tools whose identical repeat is answered from cache, never re-run.
    replay_readonly_commands: run_command binaries treated as replay-safe.
    """
    enabled: bool = True
    contract: bool = True
    brief_every: int = 3
    max_result_chars: int = 6000
    max_interventions_per_reply: int = 3
    max_interventions_per_episode: int = 6
    max_total_rounds: int = 10
    visible_batch_limit: int | None = None
    salvage: bool = True
    preflight_shell_check: bool = True
    replayable_tools: tuple = ("read_file",)
    replay_readonly_commands: tuple = READ_ONLY_COMMANDS

    ### -----------------------
    ### --- CONFIG BUILDING ---
    ### -----------------------

    @classmethod
    def from_config(cls, config: dict | None) -> "Policy":
        """Build a Policy from the loaded config dictionary.
        config: full config.toml dictionary (or None); reads the optional
                [llm.shepherd] table, ignores unknown keys, lists become tuples.
        """
        table = ((config or {}).get("llm", {}) or {}).get("shepherd", {}) or {}
        known = {f.name for f in fields(cls)}
        kwargs = {}
        for key, value in table.items():
            if key not in known:
                continue  # unknown keys are ignored so old configs never crash
            if isinstance(value, list):
                value = tuple(value)
            kwargs[key] = value
        return cls(**kwargs)

# llm_shepherd — keep small models on task in the agentic loop

> ### ⚠️ EXTERNAL PACKAGE — NOT WRITTEN BY THIS REPO'S AUTHOR
> Everything under `_vendor/` is third-party code this project **uses** but did not
> hand-write. `llm_shepherd` was designed, generated, and tested by **Claude Fable 5
> (Anthropic's AI model)** on 2026-07-09, working from a live qwen2.5:14b failure
> transcript, and is vendored in-tree (pip-style `_vendor/` convention) rather than
> pulled from PyPI. It is stdlib-only, self-contained, inert until wired in, and touches
> the host package only through its public `Provider` seam. All hand-written code in
> this repository lives outside `_vendor/`.

An **add-only** companion package to `llm/`. It wraps the LLM provider with a
deterministic supervisor (the **Shepherd**) that sits invisibly between the
`Orchestrator` and the model. **No existing file is modified** — the Shepherd
impersonates the `Provider` interface, so the untouched Orchestrator keeps
calling `user_message()` / `send_tool_results()` exactly as before.

Works with **any model and both providers** (`local` Ollama and `api`
Anthropic): everything happens at the neutral `ProviderReply`/`ToolResult`
seam, never in provider-specific code.

## Why (the recorded glitch, dissected)

A real qwen2.5:14b session burned all 6 tool steps and ended in
`PAUSE: ... Model scared and confused`. Four separate mechanics caused it:

1. **No shell, but nobody told the model.** The server runs commands via
   `subprocess.run(tokens)` — no shell. So `ls -d /home/* 2>/dev/null` hands
   `ls` the *literal* arguments `/home/*` and `2>/dev/null`. The model got
   `cannot access '/home/*': No such file or directory`, couldn't understand
   why, and kept trying shell tricks that can never work here.
2. **temperature 0 = deterministic loops.** With near-identical context and an
   identical confusing result appended each round, the model deterministically
   re-emits the *same* call. Nothing in the loop changed its input, so nothing
   changed its output. Four identical `ls -d /home/*` calls in a row.
3. **Unframed, sometimes-empty results.** A raw result gives a small model no
   receipt: did it run? is it final? is empty output an error? Ambiguity reads
   as failure, and "failure" reads as "try again".
4. **Context pressure.** Results can be huge (up to 100KB) while `num_ctx` is
   8192 — an overflowing window silently evicts the system prompt and early
   history, which is why loops strike only *sometimes*.

## What the Shepherd does

| Trick | Mechanic |
|---|---|
| **Preflight rejection** | `run_command` calls using shell operators (`\| > < ; & $( ` backtick) outside quotes are bounced *before execution* with a NO-SHELL lesson and a working alternative (`find <dir> -maxdepth 3 -name <name>`). The wasted round trip and the confusing error never happen. |
| **Replay, don't re-run** | An exact repeated call that is replay-safe (`read_file`, read-only commands like `ls`/`find`/`cat`, or anything previously `DENIED`) is answered **from cache** with "you already ran this at step #N — here is that result again". Repeats become lessons instead of loops, and the model's input *changes*, which breaks temperature-0 fixed points. |
| **Receipts, never emptiness** | Every real result is enveloped: `[TOOL RESULT #N | tool | OK/DENIED/ERROR]` header, a body that is never blank (empty output is translated to "NO MATCHES / empty file — this is a real answer"), exit-code explanations, and a FINAL footer. |
| **Just-in-time lessons** | When a result smells like the glob trap (`cannot access '/home/*'`), a NO-SHELL lesson is attached to *that* result. Small models follow corrections at the moment of error far better than upfront rules. |
| **Mission brief** | Every few rounds (and in every intervention) the model gets a compact brief: goal, numbered history with statuses, learned host facts (e.g. "paths look POSIX"), and a budget countdown. History survives context pressure. |
| **Budget endgame** | Before the Orchestrator's `max_steps` PAUSE can ever fire, the Shepherd cancels the tool phase and demands a final answer. If the model still won't answer, the user gets a **deterministic, honest summary built from the ledger** — never "scared and confused" with nothing. |
| **Text-call salvage** | If the model *writes* `{"name": "run_command", ...}` as prose instead of calling it, the Shepherd validates it against the real tool list and converts it into a genuine call. |
| **Escalation** | Interventions escalate: friendly replay → stern constrained choice ("reply with exactly ONE of: (a) one NEW call (b) your final answer"). All caps-bounded so the Shepherd itself can never loop. |

Interventions are self-fed through the provider seam, so the Orchestrator
never sees them and **never burns a visible step on them**.

## Wire-in (the only change you make, in `cli.py`)

```python
from mcp_client_console._vendor.llm_shepherd import attach          # NEW import

# inside async_main(), right after the orchestrator is built:
orchestrator = Orchestrator(session, config, tools)          # existing line
attach(orchestrator, config)                                 # NEW line
```

That's it. `attach()` wraps `orchestrator.provider` in place, reads the
optional config table below, caps itself to `max_steps - 1` so it always acts
before the PAUSE, and is safe to call twice.

## Optional config (add to your user `config.toml`, not required)

```toml
[llm.shepherd]
enabled = true                 # master switch
contract = true                # short protocol preamble on the first turn
brief_every = 3                # mission-brief refresh cadence (tool rounds)
max_result_chars = 6000        # per-result truncation (protects num_ctx)
max_total_rounds = 10          # all model round trips per user request
max_interventions_per_episode = 6
salvage = true                 # rescue tool calls written as plain text
preflight_shell_check = true   # bounce shell-operator commands before running
# replayable_tools = ["read_file"]
# replay_readonly_commands = ["ls", "cat", "find", "grep", "pwd", "..."]
```

## Verify offline (no Ollama, no server)

```bash
PYTHONPATH=src .venv/bin/python -m mcp_client_console._vendor.llm_shepherd.selftest   # 30 tests
PYTHONPATH=src .venv/bin/python -m mcp_client_console._vendor.llm_shepherd.demo      # glitch replay
```

The selftest includes a scripted replay of the recorded glitch session (one
real execution instead of six, no PAUSE) and an end-to-end run through the
**unmodified** `Orchestrator.run_turn()`.

## What it deliberately does NOT do

- Never edits your existing modules, prompts, or config defaults.
- Never blocks a *novel* mutating call — `write_file` repeats pass through
  (with a warning note) because repeating a write may be intentional.
- Never calls the model on its own beyond bounded interventions; every path
  is capped and ends in either the model's answer or a deterministic summary.
- Never touches provider-specific message formats.

## Recommended edits to EXISTING files (not applied — your call)

1. **`llm/orchestrator.py` — `DEFAULT_MODEL_PROMPT` says "The host is
   Windows"**. Your transcript host is Linux (`/home/...`). A wrong OS primes
   wrong path styles from turn one. Consider making that sentence neutral or
   config-driven. (The Shepherd partially compensates by injecting learned
   host facts, e.g. "paths look POSIX".)
2. **Server `tools.py` — `run_command` docstring** should warn: *commands run
   with NO shell; pipes/globs/redirection/`~`/`$VARS` are literal; one plain
   binary + literal args*. The model reads tool descriptions — that one line
   prevents the whole glob trap at the source. (A ready-made description
   constant ships in the server repo's `_vendor/toolshape/descriptions.py`.)
3. **`llm/provider_local.py`** — consider `"keep_alive"` and a configurable
   `num_ctx`; 8192 is tight once briefs + receipts + a few reads accumulate.

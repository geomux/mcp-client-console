# demo.py
# Offline replay of a REAL recorded qwen2.5:14b glitch session (paths anonymized), with the Shepherd
# attached. No network, no Ollama, no MCP server - a scripted fake plays the model.
# Run:  PYTHONPATH=src python -m mcp_client_console._vendor.llm_shepherd.demo

import asyncio

from mcp_client_console.llm.provider_base import ToolResult
from mcp_client_console._vendor.llm_shepherd.policy import Policy
from mcp_client_console._vendor.llm_shepherd.shepherd import Shepherd
from mcp_client_console._vendor.llm_shepherd.selftest import FakeInner, reply_call, reply_text, GLITCH_COMMAND

WIDTH = 78


### -----------------------
### --- DEMO NARRATION ----
### -----------------------

def _banner(title: str):
    """Print a section banner.
    title: section heading text.
    """
    print("_" * WIDTH)
    print(title)
    print("_" * WIDTH)


def main():
    """Replay the glitch session through the Shepherd and narrate every save."""
    _banner("WHAT ACTUALLY HAPPENED (recorded qwen2.5:14b session, paths anonymized - no shepherd)")
    print(
        "  1. ls -d /home/*/... 2>/dev/null        -> confusing garbage (no shell!)\n"
        "  2. ls -d /home/* | xargs sh -c '...'     -> confusing garbage (no shell!)\n"
        "  3. ls -d /home/*                         -> cannot access '/home/*'\n"
        "  4. ls -d /home/*   (identical repeat)    -> same result\n"
        "  5. ls -d /home/*   (identical repeat)    -> same result\n"
        "  6. ls -d /home/*   (identical repeat)    -> same result\n"
        '  => "PAUSE: stopped running after 6 tool calls. Model scared and confused."'
    )

    _banner("SAME EPISODE WITH THE SHEPHERD ATTACHED (offline scripted replay)")

    fake = FakeInner([
        reply_call("c1", "run_command", {"command": GLITCH_COMMAND}),
        reply_call("c2", "run_command", {"command": "ls /home"}),
        reply_call("c3", "run_command", {"command": "ls /home"}),
        reply_text("Your repo folder is /home/alice/projects/demo-repo."),
    ])
    shepherd = Shepherd(
        fake,
        tool_names={"run_command", "read_file", "write_file"},
        policy=Policy(visible_batch_limit=5),
    )

    async def run_episode():
        reply = await shepherd.user_message("find the filepath to my demo-repo project")
        while reply.wants_tools:
            results = []
            for call in reply.tool_calls:
                print(f"EXECUTED FOR REAL -> {call.name} {call.arguments}")
                results.append(ToolResult(call.call_id, call.name, "alice\n"))
            reply = await shepherd.send_tool_results(results)
        print()
        print(f"MODEL FINAL ANSWER: {reply.text}")

    print(f"model wants -> run_command {{'command': '{GLITCH_COMMAND[:60]}...'}}")
    print("  SHEPHERD: rejected BEFORE running (shell operator '>' with no shell) - lesson sent\n")
    asyncio.run(run_episode())

    print()
    print("what the model was told at each save:")
    print(f"  save 1: {fake.result_batches[0][0].content.splitlines()[0]}")
    print(f"  save 2: {fake.result_batches[2][0].content.splitlines()[0]}")

    _banner("SCOREBOARD")
    ledger = shepherd.ledger
    print(f"  real tool executions:        {len(ledger.steps)}   (was 6)")
    print(f"  doomed/repeat calls blocked: {ledger.blocked_calls}")
    print(f"  scared-and-confused PAUSE:   never reached")
    print(f"  final answer delivered:      yes")
    print("_" * WIDTH)


if __name__ == "__main__":
    main()

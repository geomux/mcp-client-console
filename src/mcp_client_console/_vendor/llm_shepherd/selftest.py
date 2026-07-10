# selftest.py
# Offline verification for the Shepherd - no network, no Ollama, no MCP server.
# A scripted FakeInner provider plays the model (including a replay of a real,
# path-anonymized recorded qwen2.5:14b glitch session) and every invariant is asserted.
# Run:  PYTHONPATH=src python -m mcp_client_console._vendor.llm_shepherd.selftest

import asyncio
import unittest

from mcp_client_console.llm.provider_base import Provider
from mcp_client_console.llm.provider_base import ProviderReply
from mcp_client_console.llm.provider_base import ToolCall
from mcp_client_console.llm.provider_base import ToolResult
from mcp_client_console._vendor.llm_shepherd import detectors
from mcp_client_console._vendor.llm_shepherd import envelope
from mcp_client_console._vendor.llm_shepherd import salvage
from mcp_client_console._vendor.llm_shepherd.ledger import Ledger
from mcp_client_console._vendor.llm_shepherd.policy import Policy
from mcp_client_console._vendor.llm_shepherd.shepherd import Shepherd, attach


### ------------------------
### --- SCRIPTED HELPERS ---
### ------------------------

def reply_call(call_id: str, name: str, arguments: dict) -> ProviderReply:
    """Build a tool-wanting scripted model reply.
    call_id: id for the single call.
    name: tool name.
    arguments: tool arguments dict.
    """
    return ProviderReply(text=None, tool_calls=[ToolCall(call_id, name, arguments)])


def reply_text(text: str) -> ProviderReply:
    """Build a final-text scripted model reply.
    text: the model's answer.
    """
    return ProviderReply(text=text, tool_calls=[])


class FakeInner(Provider):
    """Plays the model: pops scripted replies, records everything it was sent.
    script: list of ProviderReply objects returned in order.
    """

    def __init__(self, script: list):
        self.script = list(script)
        self.user_messages = []
        self.result_batches = []

    async def user_message(self, text: str) -> ProviderReply:
        self.user_messages.append(text)
        return self.script.pop(0)

    async def send_tool_results(self, results: list) -> ProviderReply:
        self.result_batches.append(list(results))
        return self.script.pop(0)


def assert_history_invariants(test: unittest.TestCase, fake: FakeInner):
    """Every result batch the model ever saw: non-empty string content, no blanks.
    test: the running TestCase.
    fake: the FakeInner that recorded the traffic.
    """
    for batch in fake.result_batches:
        test.assertTrue(len(batch) >= 1)
        for result in batch:
            test.assertIsInstance(result.content, str)
            test.assertTrue(result.content.strip(), "history invariant broken: empty result content")


TOOLS = {"run_command", "read_file", "write_file"}

GLITCH_COMMAND = "ls -d /home/*/.demo-repo /home/*/demo-repo /root/demo-repo 2>/dev/null"


### ----------------------------------
### --- THE RECORDED GLITCH REPLAY ---
### ----------------------------------

class TestTranscriptReplay(unittest.TestCase):
    """Replays a real qwen2.5:14b session (paths anonymized) that burned 6 rounds and PAUSEd."""

    def test_glitch_session_is_broken_in_one_execution(self):
        fake = FakeInner([
            reply_call("c1", "run_command", {"command": GLITCH_COMMAND}),   # doomed: 2> redirect
            reply_call("c2", "run_command", {"command": "ls /home"}),       # taught, now clean
            reply_call("c3", "run_command", {"command": "ls /home"}),       # exact repeat
            reply_text("Your repo folder is /home/alice/projects/demo-repo."),
        ])
        shepherd = Shepherd(fake, tool_names=TOOLS, policy=Policy(visible_batch_limit=5))

        reply = asyncio.run(shepherd.user_message("find the filepath to my demo-repo project"))
        # the doomed glob/redirect call was intercepted BEFORE execution
        self.assertTrue(reply.wants_tools)
        self.assertEqual(reply.tool_calls[0].arguments["command"], "ls /home")
        self.assertIn("NO SHELL", fake.result_batches[0][0].content)
        self.assertIn("REJECTED BEFORE RUNNING", fake.result_batches[0][0].content)

        # the test now plays Orchestrator: execute the one clean call for real
        executed = [(reply.tool_calls[0].name, reply.tool_calls[0].arguments)]
        result = ToolResult(reply.tool_calls[0].call_id, "run_command", "alice\n")
        final = asyncio.run(shepherd.send_tool_results([result]))

        # repeat was replayed from cache (never re-executed), then the answer landed
        self.assertFalse(final.wants_tools)
        self.assertIn("demo-repo", final.text)
        self.assertEqual(len(executed), 1)
        self.assertEqual(len(shepherd.ledger.steps), 1)
        self.assertIn("[TOOL RESULT #1 | run_command | OK]", fake.result_batches[1][0].content)
        self.assertIn("already ran this EXACT call at step #1", fake.result_batches[2][0].content)
        self.assertEqual(shepherd.ledger.blocked_calls, 2)

        # contract preamble rode in on the first user turn only
        self.assertTrue(fake.user_messages[0].startswith("[SUPERVISOR NOTE"))
        self.assertTrue(fake.user_messages[0].endswith("find the filepath to my demo-repo project"))
        assert_history_invariants(self, fake)


### ------------------------
### --- ENVELOPE TESTS -----
### ------------------------

class TestEnvelope(unittest.TestCase):

    def test_empty_result_is_never_delivered_empty(self):
        receipt = envelope.wrap(1, "run_command", "", 6000)
        self.assertIn("empty output", receipt)
        self.assertIn("NO MATCHES", receipt)
        self.assertIn("[TOOL RESULT #1 | run_command | OK]", receipt)
        self.assertIn("FINAL", receipt)

    def test_exit_code_classification(self):
        coarse, display, extra = envelope.classify("ls: cannot access 'x'\n[exit code 2]")
        self.assertEqual(coarse, "OK")
        self.assertEqual(display, "OK (exit 2)")
        self.assertIn("exit code 2", extra)

    def test_denied_error_and_user_denied(self):
        self.assertEqual(envelope.classify("DENIED: nope")[0], "DENIED")
        self.assertEqual(envelope.classify("ERROR: boom")[0], "ERROR")
        self.assertEqual(envelope.classify("Tool acces denied by user. You are in chat-only mode")[0], "USER_DENIED")

    def test_truncation_keeps_head_and_tail(self):
        text = ("A" * 5000) + "MIDDLE" + ("Z" * 5000)
        cut = envelope.truncate(text, 1000)
        self.assertLess(len(cut), 1200)
        self.assertTrue(cut.startswith("A"))
        self.assertTrue(cut.endswith("Z"))
        self.assertIn("characters omitted", cut)


### ------------------------
### --- DETECTOR TESTS -----
### ------------------------

class TestDetectors(unittest.TestCase):

    def test_redirect_in_glitch_command_is_flagged(self):
        self.assertIn(">", detectors.shell_operators(GLITCH_COMMAND))

    def test_quoted_operators_are_not_flagged(self):
        self.assertEqual(detectors.shell_operators('grep "a|b" file.txt'), [])
        self.assertEqual(detectors.shell_operators("grep 'x>y' file.txt"), [])

    def test_globs_are_not_hard_flagged(self):
        self.assertEqual(detectors.shell_operators("find /home -name *.py"), [])
        self.assertEqual(detectors.shell_operators("ls -d /home/*"), [])

    def test_pipes_chains_and_substitution_are_flagged(self):
        self.assertEqual(detectors.shell_operators("ls | wc -l"), ["|"])
        self.assertIn(";", detectors.shell_operators("cd /tmp; ls"))
        self.assertIn("&", detectors.shell_operators("sleep 1 && ls"))
        self.assertIn("`", detectors.shell_operators("echo `date`"))
        self.assertIn("$(", detectors.shell_operators("echo $(date)"))

    def test_glob_confusion_detector(self):
        self.assertTrue(detectors.glob_confusion("ls: cannot access '/home/*': No such file or directory"))
        self.assertFalse(detectors.glob_confusion("Desktop\nDocuments\nRepos"))

    def test_near_repeat_scoring(self):
        self.assertEqual(detectors.near_repeat("ls /home", "ls /home"), 1.0)
        self.assertLess(detectors.near_repeat("ls /home", "cat /etc/hosts"), 0.5)


### ------------------------
### --- SALVAGE TESTS ------
### ------------------------

class TestSalvage(unittest.TestCase):

    def test_salvages_known_shapes(self):
        text = 'I will run this: {"name": "run_command", "arguments": {"command": "ls /home"}}'
        calls = salvage.extract(text, TOOLS)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].name, "run_command")
        self.assertEqual(calls[0].arguments, {"command": "ls /home"})

    def test_salvages_ollama_function_shape_and_fences(self):
        text = '```json\n{"function": {"name": "read_file", "arguments": {"filepath": "/etc/hosts"}}}\n```'
        calls = salvage.extract(text, TOOLS)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].name, "read_file")

    def test_rejects_unknown_tools_and_bad_args(self):
        self.assertEqual(salvage.extract('{"name": "rm_rf", "arguments": {"x": 1}}', TOOLS), [])
        self.assertEqual(salvage.extract('{"name": "run_command", "arguments": "ls"}', TOOLS), [])
        self.assertEqual(salvage.extract("no json here at all", TOOLS), [])

    def test_dedupes_and_caps(self):
        one = '{"name": "run_command", "arguments": {"command": "ls"}}'
        calls = salvage.extract(" ".join([one] * 6), TOOLS)
        self.assertEqual(len(calls), 1)


### -----------------------------
### --- BUDGET ENDGAME TESTS ----
### -----------------------------

class TestBudgetEndgames(unittest.TestCase):

    def _spin_until_text(self, shepherd: Shepherd, first_prompt: str):
        """Mimic the Orchestrator loop: execute clean batches until a text reply.
        shepherd: the Shepherd under test.
        first_prompt: user text starting the episode.
        """
        executed = []

        async def run() -> ProviderReply:
            reply = await shepherd.user_message(first_prompt)
            while reply.wants_tools:
                results = []
                for call in reply.tool_calls:
                    executed.append(call)
                    results.append(ToolResult(call.call_id, call.name, f"ran {call.arguments}"))
                reply = await shepherd.send_tool_results(results)
            return reply

        return asyncio.run(run()), executed

    def test_force_answer_when_model_complies(self):
        script = [reply_call(f"c{i}", "run_command", {"command": f"echo {i}"}) for i in range(4)]
        script.append(reply_text("Best answer from what I gathered."))
        fake = FakeInner(script)
        policy = Policy(max_total_rounds=4, visible_batch_limit=99, contract=False)
        shepherd = Shepherd(fake, tool_names=TOOLS, policy=policy)
        final, executed = self._spin_until_text(shepherd, "do a thing")
        self.assertEqual(final.text, "Best answer from what I gathered.")
        self.assertEqual(len(executed), 3)  # 4th round hit the budget wall
        self.assertIn("CANCELLED", fake.result_batches[-1][0].content)
        assert_history_invariants(self, fake)

    def test_giveup_when_model_never_stops(self):
        script = [reply_call(f"c{i}", "run_command", {"command": f"echo {i}"}) for i in range(5)]
        fake = FakeInner(script)
        policy = Policy(max_total_rounds=4, visible_batch_limit=99, contract=False)
        shepherd = Shepherd(fake, tool_names=TOOLS, policy=policy)
        final, executed = self._spin_until_text(shepherd, "do a thing")
        self.assertFalse(final.wants_tools)
        self.assertIn("couldn't finish", final.text)
        self.assertIn("What actually ran", final.text)
        assert_history_invariants(self, fake)

    def test_batch_limit_guards_orchestrator_pause(self):
        script = [reply_call(f"c{i}", "run_command", {"command": f"echo {i}"}) for i in range(3)]
        script.append(reply_text("done early"))
        fake = FakeInner(script)
        policy = Policy(max_total_rounds=50, visible_batch_limit=2, contract=False)
        shepherd = Shepherd(fake, tool_names=TOOLS, policy=policy)
        final, executed = self._spin_until_text(shepherd, "do a thing")
        self.assertEqual(len(executed), 2)  # never reaches the Orchestrator PAUSE threshold
        self.assertEqual(final.text, "done early")


### ------------------------------------
### --- REPLAY / REPEAT / ARG TESTS ----
### ------------------------------------

class TestRepeatsAndReplay(unittest.TestCase):

    def test_read_file_repeat_is_replayed_not_rerun(self):
        fake = FakeInner([
            reply_call("r1", "read_file", {"filepath": "/etc/hosts"}),
            reply_call("r2", "read_file", {"filepath": "/etc/hosts"}),   # exact repeat
            reply_text("The hosts file maps localhost."),
        ])
        shepherd = Shepherd(fake, tool_names=TOOLS, policy=Policy(contract=False, visible_batch_limit=5))
        reply = asyncio.run(shepherd.user_message("what is in /etc/hosts?"))
        result = ToolResult("r1", "read_file", "127.0.0.1 localhost\n")
        final = asyncio.run(shepherd.send_tool_results([result]))
        self.assertFalse(final.wants_tools)
        self.assertEqual(len(shepherd.ledger.steps), 1)          # executed once only
        self.assertEqual(shepherd.ledger.blocked_calls, 1)
        replayed = fake.result_batches[1][0].content
        self.assertIn("BLOCKED", replayed)
        self.assertIn("127.0.0.1 localhost", replayed)           # cached result re-served

    def test_write_file_repeat_passes_through_with_note(self):
        fake = FakeInner([
            reply_call("w1", "write_file", {"filepath": "/tmp/x", "data_write": "hi"}),
            reply_call("w2", "write_file", {"filepath": "/tmp/x", "data_write": "hi"}),
            reply_text("Written twice."),
        ])
        shepherd = Shepherd(fake, tool_names=TOOLS, policy=Policy(contract=False, visible_batch_limit=5))
        reply = asyncio.run(shepherd.user_message("write hi"))
        ok = "OK: wrote 2 characters to /tmp/x."
        second = asyncio.run(shepherd.send_tool_results([ToolResult("w1", "write_file", ok)]))
        self.assertTrue(second.wants_tools)  # repeat NOT blocked - write is not replay-safe
        final = asyncio.run(shepherd.send_tool_results([ToolResult("w2", "write_file", ok)]))
        self.assertFalse(final.wants_tools)
        self.assertEqual(len(shepherd.ledger.steps), 2)
        noted = fake.result_batches[1][0].content
        self.assertIn("already ran this exact call at step #1", noted)
        self.assertNotIn("byte-identical", noted)  # deduped: repeat note covers it

    def test_empty_args_flagged_once_then_passed_through(self):
        fake = FakeInner([
            reply_call("b1", "run_command", {}),
            reply_call("b2", "run_command", {}),
        ])
        shepherd = Shepherd(fake, tool_names=TOOLS, policy=Policy(contract=False, visible_batch_limit=5))
        reply = asyncio.run(shepherd.user_message("do something"))
        self.assertTrue(reply.wants_tools)                        # second {} call passed through
        self.assertEqual(reply.tool_calls[0].call_id, "b2")
        self.assertIn("empty or invalid arguments", fake.result_batches[0][0].content)

    def test_denied_result_replay_blocks_hopeless_retry(self):
        fake = FakeInner([
            reply_call("d1", "run_command", {"command": "reboot now"}),
            reply_call("d2", "run_command", {"command": "reboot now"}),  # retrying a denial
            reply_text("That command is not allowed on this host."),
        ])
        shepherd = Shepherd(fake, tool_names=TOOLS, policy=Policy(contract=False, visible_batch_limit=5))
        reply = asyncio.run(shepherd.user_message("reboot the box"))
        denial = "DENIED: 'reboot' is not allowed. Allowed commands: ls, cat"
        final = asyncio.run(shepherd.send_tool_results([ToolResult("d1", "run_command", denial)]))
        self.assertFalse(final.wants_tools)
        self.assertEqual(len(shepherd.ledger.steps), 1)
        self.assertIn("BLOCKED", fake.result_batches[1][0].content)


### --------------------------------
### --- SALVAGE-IN-THE-LOOP TEST ---
### --------------------------------

class TestSalvageInLoop(unittest.TestCase):

    def test_text_written_call_is_rescued_and_noted(self):
        fake = FakeInner([
            reply_text('Let me check: {"name": "run_command", "arguments": {"command": "ls /home"}}'),
            reply_text("Found it: /home/alice."),
        ])
        shepherd = Shepherd(fake, tool_names=TOOLS, policy=Policy(contract=False, visible_batch_limit=5))
        reply = asyncio.run(shepherd.user_message("list home"))
        self.assertTrue(reply.wants_tools)
        self.assertTrue(reply.tool_calls[0].call_id.startswith("salvaged_0_"))
        final = asyncio.run(shepherd.send_tool_results(
            [ToolResult(reply.tool_calls[0].call_id, "run_command", "alice\n")]
        ))
        self.assertFalse(final.wants_tools)
        self.assertIn("rescued", fake.result_batches[0][0].content)
        self.assertEqual(shepherd.ledger.salvage_count, 1)


### ---------------------------------
### --- LESSON-ON-GLOB-TRAP TEST ----
### ---------------------------------

class TestGlobLesson(unittest.TestCase):

    def test_cannot_access_star_result_gets_no_shell_lesson(self):
        fake = FakeInner([
            reply_call("g1", "run_command", {"command": "ls -d /home/*"}),  # no hard operators
            reply_text("I see - no shell. Let me answer."),
        ])
        shepherd = Shepherd(fake, tool_names=TOOLS, policy=Policy(contract=False, visible_batch_limit=5))
        reply = asyncio.run(shepherd.user_message("list home dirs"))
        self.assertTrue(reply.wants_tools)  # soft glob passes preflight, executes for real
        raw = "ls: cannot access '/home/*': No such file or directory\n[exit code 2]"
        asyncio.run(shepherd.send_tool_results([ToolResult("g1", "run_command", raw)]))
        wrapped = fake.result_batches[0][0].content
        self.assertIn("OK (exit 2)", wrapped)
        self.assertIn("NO SHELL", wrapped)
        self.assertIn("find /home -maxdepth 3", wrapped)


### ------------------------
### --- POLICY & LEDGER ----
### ------------------------

class TestPolicyAndLedger(unittest.TestCase):

    def test_policy_from_config_overrides_and_ignores_unknowns(self):
        config = {"llm": {"shepherd": {
            "max_total_rounds": 3,
            "replay_readonly_commands": ["ls"],
            "totally_unknown_knob": 42,
        }}}
        policy = Policy.from_config(config)
        self.assertEqual(policy.max_total_rounds, 3)
        self.assertEqual(policy.replay_readonly_commands, ("ls",))
        self.assertTrue(policy.enabled)

    def test_policy_from_none_gives_defaults(self):
        policy = Policy.from_config(None)
        self.assertEqual(policy.max_total_rounds, 10)
        self.assertIn("find", policy.replay_readonly_commands)

    def test_brief_stays_compact_and_learns_host_facts(self):
        ledger = Ledger()
        ledger.begin_episode("locate my repo folder please " + "x" * 300)
        ledger.register_pending([ToolCall("a", "run_command", {"command": "ls /home"})])
        ledger.record_result("a", "run_command", "alice\n" + "/home/alice\n" * 3, "OK", 6000)
        brief = ledger.brief(rounds_left=4)
        self.assertLess(len(brief), 1500)
        self.assertIn("GOAL:", brief)
        self.assertIn("BUDGET: 4 tool rounds left.", brief)
        self.assertIn("POSIX", brief)
        for line in ledger.done_lines():
            self.assertLessEqual(len(line), 120)


### ----------------------------------------
### --- END-TO-END WITH REAL ORCHESTRATOR ---
### ----------------------------------------

class TestEndToEndOrchestrator(unittest.TestCase):
    """Proves the two-line wire-in works against the UNTOUCHED Orchestrator."""

    CONFIG = {"llm": {"provider": "local", "max_steps": 6, "local": {"model": "fake-model"}}}
    TOOL_TUPLES = [
        ("run_command", "run a command", {"type": "object", "properties": {"command": {"type": "string"}}}),
        ("read_file", "read a file", {"type": "object", "properties": {"filepath": {"type": "string"}}}),
        ("write_file", "write a file", {"type": "object", "properties": {"filepath": {"type": "string"}}}),
    ]

    def test_glitch_session_through_real_run_turn(self):
        import mcp_client_console.llm.orchestrator as orchestrator_module

        orchestrator = orchestrator_module.Orchestrator(session=None, config=self.CONFIG, tools=self.TOOL_TUPLES)
        fake = FakeInner([
            reply_call("c1", "run_command", {"command": GLITCH_COMMAND}),
            reply_call("c2", "run_command", {"command": "ls /home"}),
            reply_call("c3", "run_command", {"command": "ls /home"}),
            reply_text("Your repo lives at /home/alice/projects/demo-repo."),
        ])
        orchestrator.provider = Shepherd(fake, tool_names=set(orchestrator.tool_names),
                                         policy=Policy(visible_batch_limit=5))

        executed = []

        async def fake_run_tool(session, name, args):
            executed.append((name, args))
            return "alice\n"

        original_run_tool = orchestrator_module.run_tool
        orchestrator_module.run_tool = fake_run_tool
        try:
            text = asyncio.run(orchestrator.run_turn("find my demo-repo project"))
        finally:
            orchestrator_module.run_tool = original_run_tool

        self.assertIn("demo-repo", text)
        self.assertNotIn("PAUSE", text)                 # the scared-and-confused path never fires
        self.assertEqual(len(executed), 1)              # one real execution instead of six
        self.assertEqual(executed[0][1], {"command": "ls /home"})
        assert_history_invariants(self, fake)

    def test_attach_wires_and_never_double_wraps(self):
        import mcp_client_console.llm.orchestrator as orchestrator_module

        orchestrator = orchestrator_module.Orchestrator(session=None, config=self.CONFIG, tools=self.TOOL_TUPLES)
        original_provider = orchestrator.provider
        shepherd = attach(orchestrator, self.CONFIG)
        self.assertIsInstance(orchestrator.provider, Shepherd)
        self.assertIs(orchestrator.provider.inner, original_provider)
        self.assertEqual(shepherd.policy.visible_batch_limit, 5)  # max_steps 6 - 1
        self.assertIs(attach(orchestrator, self.CONFIG), shepherd)  # idempotent

    def test_attach_respects_enabled_false(self):
        import mcp_client_console.llm.orchestrator as orchestrator_module

        config = {"llm": {"provider": "local", "max_steps": 6, "local": {"model": "fake"},
                          "shepherd": {"enabled": False}}}
        orchestrator = orchestrator_module.Orchestrator(session=None, config=config, tools=self.TOOL_TUPLES)
        original_provider = orchestrator.provider
        returned = attach(orchestrator, config)
        self.assertIs(returned, original_provider)
        self.assertNotIsInstance(orchestrator.provider, Shepherd)


if __name__ == "__main__":
    unittest.main(verbosity=2)

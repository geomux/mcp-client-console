# shepherd.py
# The Shepherd: a supervisor that wraps any Provider and keeps small models on task.
# It impersonates the Provider interface, so the untouched Orchestrator talks to it
# exactly as it talked to the real provider. From that one seam the Shepherd can:
#   - reject doomed calls (shell syntax, bad args) BEFORE they run or burn a step
#   - answer exact repeated calls from cache instead of re-running them
#   - rewrite every tool result into an unambiguous, never-empty receipt
#   - re-inject a mission brief + budget countdown so history survives context pressure
#   - salvage tool calls the model wrote as plain text
#   - force a final answer before the Orchestrator's PAUSE ever triggers
#
# Wire-in (two lines in cli.py, nothing else changes):
#   from mcp_client_console._vendor.llm_shepherd import attach
#   attach(orchestrator, config)   # right after: orchestrator = Orchestrator(...)

from mcp_client_console.llm.provider_base import Provider
from mcp_client_console.llm.provider_base import ProviderReply
from mcp_client_console.llm.provider_base import ToolResult
from mcp_client_console._vendor.llm_shepherd import detectors
from mcp_client_console._vendor.llm_shepherd import envelope
from mcp_client_console._vendor.llm_shepherd import interventions
from mcp_client_console._vendor.llm_shepherd import salvage
from mcp_client_console._vendor.llm_shepherd.ledger import Ledger, normalize_args
from mcp_client_console._vendor.llm_shepherd.policy import Policy


### ----------------------
### --- SHEPHERD CLASS ---
### ----------------------

class Shepherd(Provider):
    """Wraps the real Provider and polices the agentic loop from inside the seam.
    inner: the real Provider (LocalProvider or ApiProvider) being wrapped.
    tool_names: set of tool names that exist on the server (for salvage validation).
    policy: Policy object with all knobs (defaults are safe).
    """

    ### ----------------------------
    ### --- Initialize the Class ---
    ### ----------------------------

    def __init__(self, inner: Provider, tool_names: set | None = None, policy: Policy | None = None):
        self.inner = inner
        self.tool_names = set(tool_names or ())
        self.policy = policy or Policy()
        self.ledger = Ledger()
        self._contract_sent = False
        self._replay_level = 0
        self._bad_args_flagged = False
        self._salvaged_ids: set[str] = set()

    ### -----------------------------------------------
    ### --- Provider Interface (Orchestrator-facing) ---
    ### -----------------------------------------------

    async def user_message(self, text: str) -> ProviderReply:
        """Start a fresh supervised episode for one user request.
        text: the user's chat prompt.
        """
        if not self.policy.enabled:
            return await self.inner.user_message(text)
        self.ledger.begin_episode(text)
        self._replay_level = 0
        self._bad_args_flagged = False
        self._salvaged_ids = set()
        outgoing = text
        if self.policy.contract and not self._contract_sent:
            outgoing = f"{interventions.contract_text()}\n{text}"
            self._contract_sent = True
        self.ledger.total_rounds += 1
        reply = await self.inner.user_message(outgoing)
        return await self._police(reply)

    async def send_tool_results(self, results: list[ToolResult]) -> ProviderReply:
        """Receive REAL executed results from the Orchestrator, envelope them, continue.
        results: ToolResult list produced by the Orchestrator's tool execution.
        """
        if not self.policy.enabled:
            return await self.inner.send_tool_results(results)
        wrapped = [self._wrap_real_result(result) for result in results]
        self.ledger.total_rounds += 1
        reply = await self.inner.send_tool_results(wrapped)
        return await self._police(reply)

    ### ------------------------------
    ### --- Result Receipt Wrapping ---
    ### ------------------------------

    def _wrap_real_result(self, result: ToolResult) -> ToolResult:
        """Turn one raw executed result into a receipt with coaching notes.
        result: the original ToolResult (never mutated - a new one is returned).
        """
        raw = str(result.content)
        coarse, _display, _extra = envelope.classify(raw)
        pending = self.ledger.pending.get(result.call_id)
        tool = result.name or (pending[0] if pending else "tool")
        args_norm = pending[1] if pending else "(unknown args)"
        prior = self.ledger.find_exact(tool, args_norm)  # must check BEFORE recording
        step = self.ledger.record_result(result.call_id, tool, raw, coarse, self.policy.max_result_chars)

        notes = []
        if result.call_id in self._salvaged_ids:
            notes.append(interventions.salvage_note())
        if prior is not None:
            notes.append(interventions.repeat_note(prior.index))
        same = self.ledger.find_same_digest(step.digest, step.index)
        if same is not None and (prior is None or same.index != prior.index):
            notes.append(interventions.identical_output_note(same.index))
        if tool == "run_command" and detectors.glob_confusion(raw):
            notes.append(interventions.no_shell_lesson())
        streak = self.ledger.error_streak()
        if streak >= 2:
            notes.append(interventions.error_streak_note(streak))
        rounds_left = self._rounds_left()
        if rounds_left <= 2:
            notes.append(interventions.budget_note(rounds_left))
        if self.policy.brief_every > 0 and step.index % self.policy.brief_every == 0:
            notes.append(self.ledger.brief(rounds_left))

        receipt = envelope.wrap(step.index, tool, raw, self.policy.max_result_chars, notes)
        return ToolResult(result.call_id, result.name, receipt)

    ### -------------------------
    ### --- The Police Loop -----
    ### -------------------------

    async def _police(self, reply: ProviderReply) -> ProviderReply:
        """Inspect a model reply; intervene until it is clean, final, or out of budget.
        reply: the model's latest ProviderReply.
        Interventions are self-fed through inner.send_tool_results, so the
        Orchestrator never sees them and never burns a step on them.
        """
        for _ in range(max(1, self.policy.max_interventions_per_reply)):
            if not reply.wants_tools:
                salvaged = self._try_salvage(reply)
                if salvaged is None:
                    return reply  # clean final text (or empty - Orchestrator handles that)
                reply = salvaged
                continue
            if self._budget_exhausted():
                return await self._force_answer(reply)
            doomed = self._preflight(reply.tool_calls)
            if not doomed:
                self.ledger.register_pending(reply.tool_calls)
                self.ledger.visible_batches += 1
                return reply  # clean tool batch - hand to Orchestrator for real execution
            if self.ledger.interventions_used >= self.policy.max_interventions_per_episode:
                return await self._force_answer(reply)
            reply = await self._intervene(reply.tool_calls, doomed)
        if reply.wants_tools:
            return await self._force_answer(reply)
        return reply

    def _budget_exhausted(self) -> bool:
        """True when no more tool rounds may be spent on this episode."""
        if self.ledger.total_rounds >= self.policy.max_total_rounds:
            return True
        limit = self.policy.visible_batch_limit
        if limit is not None and self.ledger.visible_batches >= limit:
            return True
        return False

    def _rounds_left(self) -> int:
        """Tool rounds still spendable, honoring both round and batch budgets."""
        rounds = self.policy.max_total_rounds - self.ledger.total_rounds - 1
        limit = self.policy.visible_batch_limit
        if limit is not None:
            rounds = min(rounds, limit - self.ledger.visible_batches)
        return max(0, rounds)

    ### --------------------------
    ### --- Call Preflighting ----
    ### --------------------------

    def _preflight(self, calls: list) -> dict:
        """Inspect a batch of wanted calls; map call index -> (kind, payload) for doomed ones.
        calls: the ToolCall list from the model's reply.
        Kinds: no_shell (shell operators, cannot work), replay (exact repeat with a
        cached safe answer), bad_args (empty/invalid arguments, flagged once).
        """
        doomed = {}
        for index, call in enumerate(calls):
            arguments = call.arguments if isinstance(call.arguments, dict) else {}
            if not arguments and not self._bad_args_flagged:
                self._bad_args_flagged = True
                doomed[index] = ("bad_args", None)
                continue
            if self.policy.preflight_shell_check and call.name == "run_command":
                command = str(arguments.get("command", ""))
                operators = detectors.shell_operators(command)
                if operators:
                    doomed[index] = ("no_shell", operators)
                    continue
            prior = self.ledger.find_exact(call.name, normalize_args(arguments))
            if prior is not None and self._replay_allowed(call.name, arguments, prior):
                doomed[index] = ("replay", prior)
        return doomed

    def _replay_allowed(self, tool: str, arguments: dict, prior) -> bool:
        """True when an exact repeat is safe to answer from cache instead of re-running.
        tool: tool name of the repeated call.
        arguments: the repeated call's arguments.
        prior: the ledger Step that already answered this call.
        """
        if prior.status == "DENIED":
            return True  # policy denials are deterministic - same call, same denial
        if prior.status != "OK":
            return False  # errors and user denials might genuinely change on retry
        if tool in self.policy.replayable_tools:
            return True
        if tool == "run_command":
            tokens = str(arguments.get("command", "")).split()
            return bool(tokens) and tokens[0] in self.policy.replay_readonly_commands
        return False

    ### -------------------------
    ### --- Interventions -------
    ### -------------------------

    async def _intervene(self, calls: list, doomed: dict) -> ProviderReply:
        """Self-feed synthetic results for a doomed batch and get the model's next reply.
        calls: all ToolCall objects in the model's reply.
        doomed: index -> (kind, payload) map from _preflight.
        Invariant: exactly one non-empty synthetic result per pending call.
        """
        self.ledger.interventions_used += 1
        self.ledger.blocked_calls += len(doomed)
        brief = None
        synthetics = []
        for index, call in enumerate(calls):
            if index in doomed:
                kind, payload = doomed[index]
                if kind == "no_shell":
                    command = str((call.arguments or {}).get("command", ""))
                    content = interventions.no_shell_text(command, payload)
                elif kind == "replay":
                    if brief is None:
                        brief = self.ledger.brief(self._rounds_left())
                    content = interventions.replay_text(payload, self._replay_level, brief)
                    self._replay_level += 1
                else:
                    content = interventions.bad_args_text(call.name)
            else:
                content = interventions.deferred_text(call.name)
            synthetics.append(ToolResult(call.call_id, call.name, content))
        self.ledger.total_rounds += 1
        return await self.inner.send_tool_results(synthetics)

    async def _force_answer(self, reply: ProviderReply) -> ProviderReply:
        """End the tool phase: cancel pending calls, demand an answer, guarantee text.
        reply: the tool-wanting reply that ran out of budget.
        Returns the model's answer if it complies, else a deterministic ledger summary -
        the user always gets a real reply instead of a scared-and-confused PAUSE.
        """
        brief = self.ledger.brief(rounds_left=0)
        cancel = interventions.budget_cancel_text(brief)
        synthetics = [ToolResult(call.call_id, call.name, cancel) for call in reply.tool_calls]
        self.ledger.blocked_calls += len(reply.tool_calls)
        self.ledger.total_rounds += 1
        final = await self.inner.send_tool_results(synthetics)
        if final.text and not final.wants_tools:
            return final
        return ProviderReply(text=interventions.giveup_text(self.ledger))

    ### -------------------------
    ### --- Text Salvage --------
    ### -------------------------

    def _try_salvage(self, reply: ProviderReply) -> ProviderReply | None:
        """Convert tool calls written as plain text into a real tool-call reply, or None.
        reply: a text-only ProviderReply.
        """
        if not self.policy.salvage or not reply.text or not self.tool_names:
            return None
        calls = salvage.extract(reply.text, self.tool_names)
        if not calls:
            return None
        self.ledger.salvage_count += 1
        self._salvaged_ids.update(call.call_id for call in calls)
        return ProviderReply(text=None, tool_calls=calls)


### ------------------------
### --- WIRE-IN FUNCTION ---
### ------------------------

def attach(orchestrator, config: dict | None = None) -> Provider:
    """Wrap an Orchestrator's provider with a Shepherd, in place. Safe to call once.
    orchestrator: a built Orchestrator instance (its .provider gets wrapped).
    config: the loaded config dictionary; optional [llm.shepherd] table is honored.
    Returns the Shepherd (or the untouched provider when policy disables it).
    """
    provider = getattr(orchestrator, "provider", None)
    if provider is None:
        raise ValueError("attach() needs an orchestrator that already has a .provider")
    if isinstance(provider, Shepherd):
        return provider  # already attached - never double-wrap
    policy = Policy.from_config(config)
    if not policy.enabled:
        return provider
    if policy.visible_batch_limit is None:
        max_steps = int(getattr(orchestrator, "max_steps", 6) or 6)
        policy.visible_batch_limit = max(1, max_steps - 1)
    shepherd = Shepherd(
        provider,
        tool_names=set(getattr(orchestrator, "tool_names", ()) or ()),
        policy=policy,
    )
    orchestrator.provider = shepherd
    return shepherd

# orchestrator.py
# Orchestrates the agentic AI tool loop, connects prompt text to model and tool result to final text.
# Creates a class called "Orchestrator" that objects created from can run the whole loop with.
# Uses objects (object shapes defined in provider_base.py) that are populated by provider_api.py or provider_local.py.

from mcp_client_console.client import run_tool
from mcp_client_console.llm.provider_base import ToolResult, build_provider

DEFAULT_MODEL_PROMPT = (
    "You are an agentic AI assistant that is connected to a remote server through a client console. You may access the machine only through the MCP tools provided through the remote MCP server. You may make multiple tool requests to complete you task between answering prompts. If tool outputs give you an ERROR message, adjust your angle for approaching the problem and/or explain the error/problem to the user. Focus tokens on solving the problems/prompts given to you, and keep answers short/concise."
    )

class Orchestrator:
    """Contains the active session with the MCP server and LLM provider, maintains turns between chat prompts and model actions/repsonses"""

    ### ----------------------------
    ### --- Initialize the Class ---
    ### ----------------------------

    def __init__(self, session, config: dict, tools: list):
        """Setup the orchestrator's active session, step limit, known tool names, and LLM provider.
        session: argument is live MCP session with MCP server.
        config: config dictionary- holds info uses to configure the orchestrator.
        tools: list of tuples for each tool available inside the MCP server.
        """
        llm_config = config.get("llm", {})
        self.session = session
        self.max_steps = int(llm_config.get("max_steps", 6))
        tool_names = set()
        for tool in tools:
            name, description, schema = tool # unpack the tuple in each tool's list
            tool_names.add(name)
        self.tool_names = tool_names
        self.provider = build_provider(config, tools, DEFAULT_MODEL_PROMPT)


    ### -----------------------------------
    ### --- Externally Called Functions ---
    ### -----------------------------------

    async def run_turn(self, user_input: str, on_tool=None) -> str:
        """Pass one user chat prompt, resolve any tool calls, return the tool result as model's final text.
        user_input: this argument passes the prompt from user.
        on_tool: this argument passes the tool chosen run (be switched on)
        """
        reply = await self.provider.user_message(user_input)

        steps = 0
        while reply.wants_tools:
            if steps >= self.max_steps: # this statement keeps away infinite loops / burning endless tokens
                msg = f"PAUSE: stopped running after {self.max_steps} tool calls. Model scared and confused. Ask and will retry... !"
                return f"{reply.text}\n{msg}"

            results = []
            for call in reply.tool_calls:
                if on_tool:
                    on_tool(call.name, call.arguments)
                output = await self._run_one_tool(call)
                results.append(ToolResult(call.call_id, call.name, output))

            reply = await self.provider.send_tool_results(results)
            steps += 1
        return reply.text or "NOTE: the model had not text to return..."

    ### --------------------------------
    ### --- Interally Used Functions ---
    ### --------------------------------

    async def _run_one_tool(self, call) -> str:
        """Execute a single tool call within the MCP server.
        call: a ToolCall from the model's reply, uses .name and .arguments as attributes.
        """
        if call.name not in self.tool_names:
            return f"ERROR: unknown tool '{call.name}'"
        try:
            ran_the_tool = await run_tool(self.session, call.name, call.arguments)
            return ran_the_tool
        except Exception as error:
            return f"ERROR: tool '{call.name}' failed: {error}"




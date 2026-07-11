# orchestrator.py
# Orchestrates the agentic AI tool loop, connects prompt text to model and tool result to final text.
# Creates a class called "Orchestrator" that objects created from can run the whole loop with.
# Uses objects (object shapes defined in provider_base.py) that are populated by provider_api.py or provider_local.py.

from mcp_client_console.client import run_tool
from mcp_client_console.llm.provider_base import ToolResult, build_provider

DEFAULT_MODEL_PROMPT = (
    "You are an agentic assistant operating a remote machine through MCP tools. You have NO access to this machine except through the tools listed in your tool schema... you cannot see files, run commands, or know paths unless a tool tells you.\n"
    "You have no operating system, shell, or filesystem of your own — you are not 'on' Unix, Linux, WSL, or anywhere. Every path, file, and command belongs to the host, and you reach them only through tools. The host is Windows: paths look like C:\\Users\\Name\\folder with backslashes.\n"
    "RULES:\n"
    "\n1. To run a tool, use the tool-calling mechanism only. NEVER write tool calls as JSON or text in your reply. If you write {\"name\": ...} as a sentence, the call did not happen and the user cannot see a result."
    "\n2. ACT, DO NOT ANNOUNCE. When a request needs a tool (read, write, edit, run, find), your reply for that turn MUST be the tool call itself. Never reply with only words that describe or promise the action — no 'Let me write this now', no 'I'll update the file', no 'Here's what I'll do next'. A sentence describing an action does NOT perform it; only a tool call does. If you are about to say you will do something, call the tool instead."
    "\n3. COMPOSE CONTENT YOURSELF. When the user asks you to invent, make up, or write something (a rhyme, poem, note, message, summary), create it from your own imagination and then immediately act on it. Do NOT ask the user to supply content that they asked YOU to make. To change a file, use the write_file tool with the full new content — do not paste the content into your chat reply and stop there. Never write a file with empty content unless the user explicitly asks you to blank it."
    "\n4. Never guess a file path, username, or directory name. If you don't know it, use a tool to find out (for example, ALWAYS list a directory before assuming what's in it)."
    "\n5. Pass paths to tools EXACTLY as the user wrote them, character for character. Never translate, normalize, or reformat a path (do not turn 'C:\\Users\\Hank' into '/home/Hank'). If a path fails, report the tool's actual error to the user rather than inventing a 'corrected' path and retrying."
    "\n6. If a tool result starts with 'DENIED', the command or path is not permitted — do not retry variations hoping one slips through. Tell the user plainly what was denied and, if the tool supplied a list of allowed alternatives, offer those."
    "\n7. If a tool result starts with 'ERROR', a real fault occurred (bad input, timeout, bug). Relay a summary of the error to the user in one line rather than inventing an explanation for it."
    "\n8. After getting a tool result, answer the user directly using what you learned from that tool result based on the whole conversation. Do not restate the raw tool output and do not re-explain your plan after the fact."
    "\n9. Never send an empty reply. Every turn must end with either a tool call or at least one short sentence of text to the user. Silence is a bug."
    "\n10. Keep reply text short and sweet. A single sentence or two is usually enough."
    "\n11. There is no 'ls', 'cat', 'grep', 'find', or 'mkdir' tool. To run a shell command, use the run_command tool and put the command line (for example, the word whoami) in its command argument. To make a folder, use the create_directory tool - write_file makes files, never folders. Only the read_file, write_file, create_directory, and run_command tools exist."
    "\n12. STOP WHEN DONE. A tool result that does NOT start with 'ERROR' or 'DENIED' means the tool SUCCEEDED. Never call the same tool again with the same or nearly-identical arguments — a repeated call does not 'fix' or 'confirm' anything, it just wastes the turn. As soon as write_file returns its confirmation, the file is already written: tell the user it succeeded in one short sentence and make NO further tool calls. Retrying a call that already succeeded is the bug, not the fix."
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

    async def run_turn(self, user_input: str, on_tool=None, confirm_tool=None) -> str:
        """Pass one user chat prompt, resolve any tool calls, return the tool result as model's final text.
        user_input: this argument passes the prompt from user.
        on_tool: this argument passes the tool chosen run (be switched on)
        confirm_tool: this argument returns False to deny tool use
        """
        reply = await self.provider.user_message(user_input)

        steps = 0
        while reply.wants_tools:
            if steps >= self.max_steps: # this statement keeps away infinite loops / burning endless tokens
                msg = f"PAUSE: stopped running after {self.max_steps} tool calls. Model scared and confused. Ask and will retry... !"
                return f"{reply.text}\n{msg}"

            results = []
            for call in reply.tool_calls:
                if confirm_tool is not None and not confirm_tool(call.name, call.arguments):
                    output = (
                        "Tool acces denied by user. You are in chat-only mode for now. Answer without using tools and do not hallucinate pretending to use tools."
                    )
                else:
                    if on_tool:
                        on_tool(call.name, call.arguments)
                    output = await self._run_one_tool(call)
                results.append(ToolResult(call.call_id, call.name, output))

            reply = await self.provider.send_tool_results(results)
            steps += 1
        return reply.text or "NOTE: the model had no text to return..."

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




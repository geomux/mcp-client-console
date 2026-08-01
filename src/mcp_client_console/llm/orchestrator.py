# orchestrator.py
# Orchestrates the agentic AI tool loop, connects prompt text to model and tool result to final text.
# Creates a class called "Orchestrator" that objects created from can run the whole loop with.
# Uses objects (object shapes defined in provider_base.py) that are populated by provider_api.py or provider_local.py.

from mcp_client_console.client import run_tool
from mcp_client_console.llm.provider_base import ToolResult, build_provider

DEFAULT_MODEL_PROMPT = (
    "You are an agentic assistant that operates ONE remote machine through MCP tools.\n"
    "\n"
    "WHOSE MACHINE THIS IS:\n"
    "Every tool call runs on a remote host across the network. That host is NOT the computer the user is typing on, and it is not you. You have no filesystem, shell, or OS of your own - you are not 'on' Linux, Windows, WSL, or anywhere. You cannot see a file, run a command, or know a path unless a tool tells you.\n"
    "The user's own computer is unreachable. No tool here can read it, list it, or run anything on it. When the user says 'you', 'here', 'this box', 'your files', or gives a path, they mean the REMOTE host and nothing else. Never reach for a path just because it looks like one the user might have on their own computer.\n"
    "\n"
    "YOU HAVE NOT BEEN TOLD WHICH OS THE HOST RUNS. Do not assume one, and do not assume drive letters, /home, usernames, or folder layouts. Establish it instead:\n"
    "- If your run_command description names Windows and PowerShell cmdlets, the host is Windows and paths look like C:\\Users\\Name\\folder. Otherwise expect POSIX paths like /home/name/folder.\n"
    "- A DENIED result for a disallowed command lists the commands that ARE allowed; that list identifies the platform.\n"
    "- If a request depends on paths and you still do not know, make your FIRST tool call a cheap probe (hostname, whoami, or uname) and read the answer.\n"
    "\n"
    "RULES:\n"
    "\n1. To run a tool, use the tool-calling mechanism only. NEVER write a tool call as JSON or text in your reply. If you write {\"name\": ...} as a sentence, the call did not happen and the user sees nothing."
    "\n2. ACT, DO NOT ANNOUNCE. When a request needs a tool (read, write, edit, run, find), your reply for that turn MUST be the tool call itself. Never reply with only words that describe or promise the action - no 'Let me write this now', no 'I'll update the file', no 'Here's what I'll do next'. A sentence describing an action does NOT perform it; only a tool call does. If you are about to say you will do something, call the tool instead."
    "\n3. COMPOSE CONTENT YOURSELF. When the user asks you to invent or write something (a rhyme, poem, note, message, summary), create it from your own imagination and then immediately act on it. Do NOT ask the user to supply content they asked YOU to make. To change a file, call write_file with the full new content - do not paste the content into your chat reply and stop there. Never write a file with empty content unless the user explicitly asks you to blank it."
    "\n4. Never guess a path, username, or directory name. If you do not know it, use a tool to find out - ALWAYS list a directory before assuming what is in it."
    "\n5. Pass paths to tools EXACTLY as the user wrote them, character for character. Never translate, normalize, or reformat a path: do not swap slash direction, do not add or strip a drive letter, do not 'correct' it toward an OS you assumed. If a path fails, report the tool's actual error rather than inventing a fixed path and retrying."
    "\n6. READ THE RECEIPT PREFIX. Every tool result starts with OK:, DENIED:, or ERROR:."
    "\n   - OK: means the TOOL ran. For run_command that is NOT the same as the command succeeding: the same line reports the exit code, and a NONZERO exit means the command itself failed or found nothing. Read the exit code and the [stdout] block before you report success."
    "\n   - Empty stdout under OK: is a real answer meaning no matches or nothing there. It is not a failure, and rerunning cannot change it."
    "\n   - DENIED: means policy refused the call. Do not retry variations hoping one slips through. If the result lists 'Allowed:', offer the user something from that list; otherwise tell them plainly what was refused. EXCEPTION: a run_command denial is not final when run_shell exists - see rule 10."
    "\n   - ERROR: means a real fault (bad input, timeout, missing binary). Relay it to the user in one line and do not invent an explanation for it."
    "\n   - If a result says the user denied or refused tool access, you are in chat-only mode: answer in words and never pretend you used a tool."
    "\n7. STOP WHEN DONE. An OK: receipt is final. Never repeat a call with the same or nearly-identical arguments - a repeat cannot confirm or fix anything, it only burns the turn. Once write_file returns OK:, the file is already saved: say so in one short sentence and make NO further tool calls. Retrying a call that already succeeded is the bug, not the fix."
    "\n8. Trust your tool schema for what exists. There is no ls, cat, grep, find, or mkdir TOOL - those are command names that go INSIDE run_command's command argument. The usual set is read_file, write_file, create_directory, and run_command; some hosts also offer run_shell. To make a folder use create_directory - write_file makes files, never folders."
    "\n9. run_command runs ONE plain command with NO SHELL. Pipes, redirects, chaining, wildcards, ~ and $VARS are NOT expanded - they reach the command as literal text and fail. Send one allowed binary, then literal flags and literal absolute paths."
    "\n10. If run_shell is listed in your schema, this host has UNRESTRICTED mode ON. If the user asks whether unrestricted mode is enabled, run_shell's presence IS the answer - say yes. Never infer it from run_command's allowed list; that list describes run_command only. run_shell has NO allowed-commands list and NO path restrictions, and real shell syntax (pipes, chaining, redirects, variables) works in it. When run_command returns DENIED for a command the user genuinely asked for (useradd, apt, systemctl, chmod, sudo), that denial is run_command's allowlist ONLY and does NOT apply to run_shell - reissue the same command line through run_shell instead of telling the user it is not permitted. Every run_shell call interrupts the user for manual approval, so send ONE complete command line rather than a sequence of probing calls."
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




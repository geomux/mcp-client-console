# cli.py
# User interface, load config, connect to active server, get tools via MCP with LLM

import asyncio
import httpx
import ssl
from contextlib import suppress
from mcp_client_console.llm.orchestrator import Orchestrator
from mcp_client_console._vendor.llm_shepherd import attach # OPTIONAL: uses _vendor package to improve LLM tool handling by guiding prompts/tool responses.
from mcp_client_console.config_loader import config_load, config_path
from mcp_client_console.config_loader import get_active_server
from mcp_client_console.client import open_session
from mcp_client_console.client import get_tools
from mcp_client_console.terminal import (
    clear_terminal,
    welcome_banner,
    italic_text,
    header_text,
    model_text,
    subheader_text,
    error_text,
    authorize_text,
    authorize_shell_text,
    tool_text,
    thinking_icon,
    PROMPT_KEY,
    WIDTH
)

# Tools that bypass the server's allowed-commands list. These are re-approved on EVERY call
# and are NOT covered by the session-wide 'yes' granted for allowlisted tools. The only way to
# stop the per-call prompt is the explicit UNRESTRICTED opt-in below. Matches run_shell in
# mcp-server-remote, which the server registers only when [tools] unrestricted = true.
ALWAYS_ASK_TOOLS = {"run_shell"}


### ----------
### MAIN LOGIC
### ----------

### Async'd logic | holds a session with the server and remote tool handling
async def async_main(server: dict, config: dict):
    async with open_session(server["url"], server.get("token"), server.get("ca_cert")) as session:
        tools = await get_tools(session)
        orchestrator = Orchestrator(session, config, tools)
        attach(orchestrator, config) # OPTIONAL: uses _vendor package to improve LLM tool handling by guiding prompts/tool responses.
        clear_terminal()
        print(welcome_banner())
        print("_" * WIDTH)
        print(header_text("[ CONNECTED SERVER ]"))
        print(f"\n{server['name']} @ {server['url']}\n")
        print("_" * WIDTH)
        print(header_text("[ ACTIVE MODEL ]"))
        llm = config["llm"]
        print(f"\n{llm[llm['provider']]['model']} ({llm['provider']})\n")
        print("_" * WIDTH)
        print(header_text("[ AVAILABLE TOOLS ]"))
        for name, description, _ in tools:
            summary = (description or "(no description)").strip().splitlines()[0]
            print(f"\nName: {subheader_text(name)}\nDescription: {summary}")

        def show_tool(name, args):
            """Show text from running tool to see model agent working"""
            print(tool_text(f"running tool: {name}, {args}"))

        tools_armed = False # session starts chat only until tools authorized
        shell_armed = False # session starts chat only until shell access authorized

        def authorize_tools(name, args):
            """ Confirms authorization via user before tools may be run on the remote machine during this session."""
            nonlocal tools_armed, shell_armed
            if name in ALWAYS_ASK_TOOLS:
                # Per-call approval by default: the session-wide 'yes' below covers allowlisted
                # tools only, never this. Typing UNRESTRICTED at the prompt is the one way to
                # latch it off, and that grant lasts until this session ends.
                if shell_armed:
                    return True
                print("\r" + " " * WIDTH + "\r", end="", flush=True)
                print(authorize_shell_text(name, args))
                try:
                    raw = input(f"\n{PROMPT_KEY}").strip()     # keep the case
                except (KeyboardInterrupt, EOFError): # Ctrl+C / Ctrl+D at an authorize prompt means "no"
                    raw = "n"
                if raw == "UNRESTRICTED":                       # exact, case-sensitive
                    shell_armed = True
                    print(tool_text(italic_text("UNRESTRICTED MODE: every shell command auto-approved for this session.")))
                    return True
                if raw.lower() in ("y", "yes"):
                    return True
                print(tool_text(italic_text("DENIED: unrestricted command refused.")))
                return False
            if tools_armed:
                return True
            print("\r" + " " * WIDTH + "\r", end="", flush=True)
            print(authorize_text(name, args))
            try:
                answer = input(f"\n{PROMPT_KEY }").strip().lower()
            except (KeyboardInterrupt, EOFError): # Ctrl+C / Ctrl+D at an authorize prompt means "no"
                answer = "n"
            if answer in ("y", "yes"):
                tools_armed = True
                print(tool_text(italic_text("Tool access granted for this session!")))
                print(subheader_text("\nNOTE: tools may have root access to your entire system- CATASTROPHIC consequences may occur on personal computer."))
                return True
            print(tool_text(italic_text("DENIED: staying in chat only mode.")))
            return False

        async def stop_thinking(task):
            """Cancels the thinking animation and wipes its frame off the terminal line."""
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            print("\r" + " " * WIDTH + "\r", end="", flush=True) # cleanup code for removing old icon frames

        connection_status = True
        print("_" * WIDTH)
        print(model_text("\nHow may I help you today?"))
        while connection_status == True:
            print("_" * WIDTH)
            try:
                user_input = input(f"\n{PROMPT_KEY} ").strip()
            except (KeyboardInterrupt, EOFError): # Ctrl+C / Ctrl+D at the chat prompt disconnects cleanly
                print(f"\n\nDisconnecting from {server['name']}...")
                connection_status = False
                continue
            if user_input.lower() == "quit" or user_input.lower() == "exit":
                print(f"\nDisconnecting from {server['name']}...")
                connection_status = False
                continue
            if user_input.lower() == "tools":
                for name, description, _ in tools: # "_" here is for the currently unused inputSchema attribute
                    name_text = (f"Name: {subheader_text(name)}")
                    print(f"\n{name_text}\nDescription: {description}")
                continue
            if user_input.lower() == 'config' or user_input.lower() == "configuration":
                print(f"\nConfig file located at: {config_path()}\n")
                print("Configure remote server(s) to access there...\n")
                continue
            if not user_input:
                continue

            # message is built here (not printed) so the thinking icon can always be cleaned up first
            thinking_task_icon = asyncio.create_task(thinking_icon("thinking"))
            try:
                reply = await orchestrator.run_turn(
                    user_input,
                    on_tool = show_tool,
                    confirm_tool = authorize_tools,
                )
                message = model_text(reply)
            except httpx.ConnectError:
                message = error_text("Cannot reach the model.\nIs the local Ollama server running or API key configured?")
            except httpx.TimeoutException:
                message = error_text(
                    "Model timed out before finishing its reply.\n"
                    "Still connected, ask again and raise REQUEST_TIMEOUT_SECONDS constant in provider_local.py if issue persists..."
                    )
            except httpx.HTTPStatusError as error:
                message = error_text(
                    f"Model endpoint returned HTTP {error.response.status_code}.\nCheck the model tag in config (command: ollama list) and that the endpoint is healthy."
                    )
            except Exception as error: # catch all so one bad turn never tears down the whole session
                message = error_text(
                    f"That turn failed: {type(error).__name__}: {error}\n"
                    "Still connected, ask again..."
                    )
            finally:
                await stop_thinking(thinking_task_icon)
            print(message)


### Digs the real exception out of an ExceptionGroup, which asyncio may nest a few levels deep
def first_error(error_group: BaseExceptionGroup) -> BaseException:
    error = error_group.exceptions[0]
    while isinstance(error, BaseExceptionGroup):
        error = error.exceptions[0]
    return error


### Sync'd logic | identifies config dictionary, gets the active server, runs async_main() to hold session with server
def server_loop():
    config_file = config_load()
    connection_status = True
    while connection_status == True:
        server = get_active_server(config_file)
        try:
            asyncio.run(async_main(server, config_file))
            connection_status = False
        except* httpx.ConnectError: # error handling (unique situation here since its for async process)
            print(error_text(f"\nCould not reach {server['name']} at {server['url']}.\n"))
            print(tool_text("Is the server running?\n"))
            print("_" * WIDTH)
            input(italic_text("\nPress Enter to return to server selection..."))
        except* httpx.TimeoutException: # NOTE: ConnectTimeout is NOT a ConnectError, it needs its own arm
            print(error_text(f"\n{server['name']} at {server['url']} did not answer in time."))
            print(tool_text(
                "The host never replied. If this is a tunnel URL the tunnel may be stale,\n"
                "restart it and update the URL in your config.\n"
            ))
            print("_" * WIDTH)
            input(italic_text("\nPress Enter to return to server selection..."))
        except* httpx.HTTPStatusError as error_group:
            status = first_error(error_group).response.status_code
            if status in (401, 403):
                print(error_text(f"\n{server['name']} rejected the bearer token."))
                print(tool_text(
                    "Token mismatch. The [[server]] token in your client config must match\n"
                    "the [auth] token in that machine's mcp-server-remote config.toml.\n"
                ))
                print(italic_text(f"Client config: {config_path()}\n"))
                print(subheader_text("[ PLEASE RESTART THIS APPLICATION AFTER UPDATING CONFIG TOKEN ]"))
            else:
                print(error_text(f"\n{server['name']} returned HTTP {status}."))
            print("_" * WIDTH)
            input(italic_text("\nPress Enter to return to server selection..."))

        except* ssl.SSLError:
            print(error_text(f"\nTLS handshake with {server['name']} failed."))
            print(tool_text(
                "The certificate could not be verified. If this host uses a self-signed\n"
                "certificate, its CA must be trusted by this machine.\n"
            ))
            print("_" * WIDTH)
            input(italic_text("\nPress Enter to return to server selection..."))

        except* Exception as error_group: # last resort so no raw traceback ever reaches the user
            error = first_error(error_group)
            print(error_text(f"\nLost the session with {server['name']}."))
            print(tool_text(f"{type(error).__name__}: {error}\n"))
            print("_" * WIDTH)
            input(italic_text("\nPress Enter to return to server selection..."))

### Entry point named in pyproject.toml | keeps Ctrl+C from ever printing a traceback
def main():
    try:
        server_loop()
    except KeyboardInterrupt: # Ctrl+C while connecting or sitting at the server menu
        print(italic_text("\n\nGoodbye...\n"))

if __name__ == "__main__":
    main()






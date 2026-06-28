# cli.py
# User interface, load config, connect to active server, get tools via MCP with LLM

import asyncio
import httpx
import os
from mcp_client_console.llm.orchestrator import Orchestrator
from mcp_client_console.config_loader import config_load
from mcp_client_console.config_loader import get_active_server
from mcp_client_console.client import open_session
from mcp_client_console.client import get_tools
from mcp_client_console.client import run_tool
from mcp_client_console.terminal import (
    clear_terminal,
    welcome_banner,
    italic_text,
    header_text,
    model_text,
    subheader_text,
    error_text,
    tool_text,
    thinking_icon,
    PROMPT_KEY,
)


### ----------
### MAIN LOGIC
### ----------

### Async'd logic | holds a session with the server and remote tool handling
async def async_main(server: dict, config: dict):
    async with open_session(server["url"]) as session:
        tools = await get_tools(session)
        orchestrator = Orchestrator(session, config, tools)
        clear_terminal()
        print(welcome_banner())
        print("_" * 50)
        print(header_text("[ CONNECTED SERVER ]"))
        print(f"\n{server['name']} @ {server['url']}\n")
        print("_" * 50)
        print(header_text("[ AVAILABLE TOOLS ]"))
        for name, description, _ in tools: # "_" here is for the currently unused inputSchema attribute
            name_text = subheader_text(f"Name: {name}")
            print(f"\n{name_text}\nDescription: {description}")

        def show_tool(name, args):
            """Show text from running tool to see model agent working"""
            print(tool_text(f"running tool: {name}, {args}"))


        connection_status = True
        while connection_status == True:
            print("_" * 50)
            print(model_text("How may I help you today?"))
            user_input = input(f"\n{PROMPT_KEY} ").strip()
            if user_input.lower() == "quit" or user_input.lower() == "exit":
                print(f"\nDisconnecting from {server['name']}...")
                connection_status = False
                continue
            if not user_input:
                continue

            try:
                thinking_task_icon = asyncio.create_task(thinking_icon("thinking"))
                reply = await orchestrator.run_turn(user_input, on_tool=show_tool)
                thinking_task_icon.cancel()
                print("\r" + " " * 20 + "\r", end="") # cleanup code for removing old icon frames
                print(model_text(reply))
            except httpx.ConnectError:
                thinking_task_icon.cancel()
                print("\r" + " " * 20 + "\r", end="") # cleanup code for removing old icon frames
                print(error_text("Cannot reach the model.\nIs the local Ollama server running or API key configured?"))

        #reply = await orchestrator.run_turn(user_input, on_tool=show_tool)


### Sync'd logic | identifies config dictionary, gets the active server, runs async_main() to hold session with server
def main():
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
            print("_" * 50)
            input(italic_text("\nPress Enter to return to server selection..."))


if __name__ == "__main__":
    main()






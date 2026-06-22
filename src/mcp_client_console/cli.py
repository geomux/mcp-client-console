# cli.py
# User interface, load config, connect to active server, get tools via MCP with LLM

import asyncio
import httpx
import sys
from mcp_client_console.config_loader import config_load
from mcp_client_console.config_loader import get_active_server
from mcp_client_console.client import open_session
from mcp_client_console.client import get_tools
from mcp_client_console.client import run_tool

### -------
### CLI GUI
### -------
RESET = "\033[0m"
BOLD_GREEN = "\033[1;32m"
BOLD_BLUE = "\033[1;34m"
BOLD_RED = "\033[1;31m"
BRIGHT_MAGENTA = "\033[95m"

PROMPT_KEY = f"{BOLD_GREEN}>: {RESET}" # colorful UI settings for console chat prompt key.
def header_text(text: str) -> str:
    """Styles passed string to fancy header formatting"""
    return f"{BOLD_BLUE}{text}{RESET}"

def model_text(text: str) -> str:
    """Styles passed string to fancy model text formatting"""
    return f"\n{BRIGHT_MAGENTA}MODEL: {text}{RESET}"

def subheader_text(text: str) -> str:
    return f"{BOLD_GREEN}{text}{RESET}"

def error_text(text: str) -> str:
    """Styles passed string to fancy error text formatting"""
    return f"\n{BOLD_RED}ERROR: {text}{RESET}"





### ----------
### MAIN LOGIC
### ----------

### Async'd logic | holds a session with the server and remote tool handling
async def async_main(server: dict):
    async with open_session(server["url"]) as session:
        tools = await get_tools(session)
        print(f"\n"*3)
        print(subheader_text("...session begin...hello..."))
        print(f"\n"*3)
        print("_" * 50)
        print(header_text("[ CONNECTED SERVER ]"))
        print(f"\n{server['name']} @ {server['url']}\n")
        print("_" * 50)
        print(header_text("[ AVAILABLE TOOLS ]"))
        for name, description, _ in tools: # "_" here is for the currently unused inputSchema attribute
            print(f"\nName: {name}\nDescription:{description}")
        print("_" * 50)
        print(f"\nEnter 'quit' or 'exit' to disconnect from server at anytime.")
        print("\nType below to access remote MCP server with agentic model...")
        connection_status = True
        while connection_status == True:
            print("_" * 50)
            print(model_text("How may I help you today?"))
            user_input = input(f"\n{PROMPT_KEY} ").strip()
            if user_input.lower() == "quit" or user_input.lower() == "exit":
                print(f"\nDisconnecting from {server['name']}...")
                connection_status = False
            if not user_input:
                continue

        ### ---
        ### Section below to be replaced with LLM connections
        ### Section below temporary hardcoded to run a test get_time() tool via MCP
        ### ---
        result = await run_tool(session, "get_time", {})
        print(f"\n[ NO LLM YET ] result of get_time() is: {result}")

### Sync'd logic | identifies config dictionary, gets the active server, runs async_main() to hold session with server
def main():
    config_file = config_load()
    connection_status = True
    while connection_status == True:
        server = get_active_server(config_file)
        try:
            asyncio.run(async_main(server))
            print(subheader_text("\n...session over...goodbye...\n"))
            connection_status = False
        except* httpx.ConnectError: # error handling (unique situation here since its for async process)
            print("_" * 50)
            print(error_text(f"\nCould not reach {server['name']} at {server['url']}."))
            print("\nIs the server running?\n")
            print("_" * 50)


if __name__ == "__main__":
    main()






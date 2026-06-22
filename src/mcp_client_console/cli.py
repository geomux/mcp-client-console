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

### Async'd logic | holds a session with the server and remote tool handling
async def async_main(server: dict):
    async with open_session(server["url"]) as session:
        tools = await get_tools(session)
        print("_" * 50)
        print(f"\n[ CONNECTED ]")
        print(f"\n{server['name']} @ {server['url']}\n")
        print("_" * 50)
        print(f"\n[ AVAILABLE TOOLS]")
        for name, description, _ in tools: # "_" here is for the currently unused inputSchema attribute
            print(f"\nName: {name}\nDescription:{description}")
        print("_" * 50)
        print(f"\nEnter 'quit' or 'exit' to disconnect from server")
        connection_status = True
        while connection_status == True:
            user_input = input(">: ").strip()
            if user_input.lower() == "quit" or user_input.lower() == "exit":
                print(f"Disconnecting from {server['name']}...")
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
            print("...session begin...hello...")
            asyncio.run(async_main(server))
            print("...session over...goodbye...")
            connection_status = False
        except* httpx.ConnectError: # error handling (unique situation here since its for async process)
            print("_" * 50)
            print(f"\nERROR: Could not reach {server['name']} at {server['url']}.")
            print("\nIs the server running?\n")
            print("_" * 50)


if __name__ == "__main__":
    main()






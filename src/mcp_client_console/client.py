# client.py
# Speaks MCP (within Streamable HTTP packets) to a remote MCP server - opens a session, lists tools, runs tools.
### ...lots of notes below because complicated...

from contextlib import asynccontextmanager
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

### Opens a session with MCP server, the connection between client<-->server includes two layers
### 1. streamablehttp_client: handles HTTP read & write streams
### 2. ClientSession: handles MCP within HTTP stream packets
@asynccontextmanager # @asynccontextmanager sticks MCP to HTTP both (plus the initialize server handshake)
async def open_session(url: str): #returns ClientSession
    ### ---
    ### PLACEHOLDER code below for later when including Authentication with Bearer Token
    ### headers={"Authorization": f"Bearer {token}"}
    ### ---
    async with streamablehttp_client(url) as (read_stream, write_stream, get_session_id): # HTTP layer
        async with ClientSession(read_stream, write_stream) as session: # MCP layer
            await session.initialize() # IMPORTANT: MCP handshake here - protocol version + capabilities set
            yield session

### Get list of tools available in MCP server
async def get_tools(session: ClientSession) -> list[tuple[str, str | None, dict]]:
    response = await session.list_tools()
    tool_list = []
    for tool in response.tools:
        temp_tuple = (tool.name, tool.description, tool.inputSchema)
        tool_list.append(temp_tuple)
    return tool_list

### Run a specified tool in MCP server, return its result in text
async def run_tool(session: ClientSession, name: str, args: dict) -> str:
    tool_picked = await session.call_tool(name, args)
    text_parts = []
    for part in tool_picked.content:
        if part.type == "text":
            text_parts.append(part.text)
    message = "\n".join(text_parts)
    return message

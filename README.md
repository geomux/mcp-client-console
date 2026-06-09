# mcp-client-console

MCP client that connects to a remote MCP server, LLM backend (API key or local model) and preset configuration files.

## Architecture Flowchart

{user} <--> mcp-client-console <--> HTTPS <--> {box} <--> mcp-server-remote <--> tools

## User Guide | Installation

### Users: install commands
    pipx install mcp-client-console
    
### Developers: install commands
    git clone https://github.com/geomux/mcp-client-console.git
    cd mcp-client-console
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e .

## User Guide | Configuration

Populate the "config.toml" file, located in the project root. 

*The client reads from "config.toml" to locate and access remote MCP server.*

EXAMPLE:
```
[server]
name = "Box_1"
url = "http://127.0.0.1:9000/mcp"
```

    
## User Guide | Operation

Start your MCP server first, see related / requires repos below.

Confirm the MCP client is configured to connect to the remote server location.

*The client connects, performs MCP handshake, lists the available tools via the server.*

Use LLM natural language processing in CLI to access tools on remote box.

EXAMPLE:
```
:~$ mcp-client-console
Connected to Box_1 @ http://127.0.0.1:9000/mcp
___

How may I help you today?

```

## Related / Required Repos

### mcp-server-remote
    https://github.com/geomux/mcp-server-remote

### mcp-gateway-remote
    https://github.com/geomux/mcp-gateway-remote


## --
## Project Status
## --
- [x] Create MCP client repo
- [ ] Connect to MCP server locally
- [ ] LLM backend (API / local Ollama) added to client
- [ ] Connect to MCP server remotely with TLS + bearer auth



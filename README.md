# mcp-client-console

MCP client that connects to a remote MCP server, LLM backend (API key or local model) and preset configuration files.

*Intended for use within private network for Cybersecurity purposes.*

```
System:  {user} <--> mcp-client-console <--> network <--> {box} <--> mcp-server-remote <--> tools
Client:  {user} <--> cli.py <--> client.py <--> mcp SDK <--> * <--> mcp-server-remote
```

## User Guide | LLM Backend Setup

*Skip this section if using an API LLM connection.* For a local model, set up Ollama before installing the client:

```bash
curl -fsSL https://ollama.com/install.sh | sh   # Linux. macOS: brew install ollama. Windows: winget install Ollama.Ollama
ollama pull qwen2.5:14b                         # default model in config_default.toml
ollama list                                     # confirm Ollama is running and the model is pulled
```

To use a different model, pull it the same way and update `model` under `[llm.local]` in your `config.toml` to match the tag exactly. `host` under `[llm.local]` must include the full scheme: `http://127.0.0.1:11434` — not `127.0.0.1:11434`.

## User Guide | Installation

Users:

```bash
pipx install mcp-client-console
mcp-client-console
```

Developers:

```bash
git clone https://github.com/geomux/mcp-client-console.git
cd mcp-client-console
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
mcp-client-console
```

## User Guide | Configuration

First run creates a default `config.toml` and prints its filepath (the `/config` command in the terminal chat prints it too). Edit it — populate with server name, url, token:

```toml
[server]
name = "Box_1"
url = "http://127.0.0.1:9000/mcp"
```

| OS      | Config filepath                                                |
| ------- | -------------------------------------------------------------- |
| Linux   | `~/.config/mcp-client-console/config.toml`                     |
| macOS   | `~/Library/Application Support/mcp-client-console/config.toml` |
| Windows | `%LOCALAPPDATA%\mcp-client-console\config.toml`                |

## User Guide | Operation

Start your MCP server first (see repos below) and confirm the client is configured to reach it. The client connects, performs the MCP handshake, and lists the server's tools. Use LLM natural language in the CLI to access tools on the remote box:

```
$ mcp-client-console
Connected to Box_1 @ http://127.0.0.1:9000/mcp

How may I help you today?
```

## Related / Required Repos

- [mcp-server-remote](https://github.com/geomux/mcp-server-remote)
- [mcp-gateway-remote](https://github.com/geomux/mcp-gateway-remote)

## Project Status

- [x] Create MCP client repo
- [x] Connect to MCP server locally
- [x] LLM backend (API / local Ollama) added to client
- [ ] Connect to MCP server remotely with TLS + bearer auth

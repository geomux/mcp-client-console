# provider_local
# Interface with local LLM using native Ollama server /api/chat tool calling format.
# Passed through provider_base.py to convert to neutral types in order to be used by Orchestrator.

import json
import httpx
from mcp_client_console.llm.provider_base import Provider
from mcp_client_console.llm.provider_base import ProviderReply
from mcp_client_console.llm.provider_base import ToolCall
from mcp_client_console.llm.provider_base import ToolResult

REQUEST_TIMEOUT_SECONDS = 300

### ----------------------------------
### --- MODEL PROVIDER LOCAL CLASS ---
### ----------------------------------

class LocalProvider(Provider):
    """ Local LLM, Ollama Provider, Ollama default endpoint: http://127.0.0.1:11434/api/chat"""
    def __init__(self, config: dict, tools: list, prompt: str):
        local_config = config.get("llm", {}).get("local", {})
        self.model = local_config.get("model", None)
        host = local_config.get("host", "http://127.0.0.1:11434").rstrip("/")
        self.chat_url = f"{host}/api/chat"
        self.tools = self._build_tool_defs(tools)
        self.messages = [{"role": "system", "content": prompt}]

    ### -----------------------------------
    ### --- FORMAT CONVERSION FUNCTIONS ---
    ### -----------------------------------

    def _build_tool_defs(self, tools: list) -> list:
        """ Convert MCP tool tuples (name, description, input_schema) to Ollama tool definition schema"""
        definitions = []
        for name, description, input_schema in tools:
            definitions.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description or "",
                        "parameters": input_schema or {
                            "type": "object",
                            "properties": {}
                            },
                        },
                    }
                )
        return definitions

    def _parse_reply(self, message: dict) -> ProviderReply:
        """ Convert local model reply to neutral ProviderReply object from provider_base.py"""
        tool_calls = []
        for index, raw in enumerate(message.get("tool_calls") or []):
            function = raw.get("function", {})
            arguments = function.get("arguments") or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            name = function.get("name", "")
            tool_calls.append(ToolCall(call_id=f"call_{index}_{name}", name=name, arguments=arguments))
        text = message.get("content") or None
        return ProviderReply(text=text, tool_calls=tool_calls)

    ### ---------------------------
    ### --- LOCAL CHAT HANDLING ---
    ### ---------------------------

    async def _chat(self) -> ProviderReply:
        """ Main chatting function. Captures message history, sends to local model chat endpoint, handles reply."""
        package = {
                "model": self.model,
                "messages": self.messages,
                "tools": self.tools,
                "stream": False,
        }
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as http_client:
            response = await http_client.post(self.chat_url, json=package)
            response.raise_for_status()
            data = response.json()

        message = data.get("message", {})
        self.messages.append(message)
        return self._parse_reply(message)

    async def user_message(self, text: str) -> ProviderReply:
        """ Append user's message to the conversation with the local model."""
        self.messages.append({"role": "user", "content": text})
        return await self._chat()

    async def send_tool_results(self, results: list[ToolResult]) -> ProviderReply:
        """ Append tool results to the conversation with the local model."""
        for result in results:
                self.messages.append({
                        "role": "tool",
                        "tool_name": result.name,
                        "content": result.content,
                })
        return await self._chat()


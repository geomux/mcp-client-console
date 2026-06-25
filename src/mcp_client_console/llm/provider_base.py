# provider_base.py
# Base classes define neutral objects for Orchestrator to interface with  LLM provider types.

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


### ----------------------------
### --- NEUTRAL TYPE CLASSES ---
### ----------------------------

@dataclass
class ToolCall:
    """Holds the model's request to run a tool.
    call_id: linking key to match result of tool call back to the original call.
    name: tool called
    arguments: arguments passed through the tool
    """
    call_id: str
    name: str
    arguments: dict

@dataclass
class ToolResult:
    """Holds the result from running ToolCall.
    call_id: linking key to match result of tool call back to the original call.
    name: tool ran
    content: result of running the tool
    """
    call_id: str
    name: str
    content: dict

@dataclass
class ProviderReply:
    """ Holds model's decision after recieving ToolResult- either final text response to user OR run another ToolCall.
    text: model's response from running the tool
    """
    text: str | None = None # text: str IF final reply to user OR None if model wants to run another tool.
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def wants_tools(self) -> bool:
        return len(self.tool_calls) > 0

### ---------------------------------
### --- MODEL PROVIDER BASE CLASS ---
### ---------------------------------

class Provider(ABC):
    """ Holds a stateful conversation with the LLM."""
    @abstractmethod
    async def send_message(self, text: str) -> ProviderReply:
        """Append a user message, call the model, return its reply"""
        print(f"send_message called with: {text}")

    @abstractmethod
    async def send_tool_result(self, result: list[ToolResult]) -> ProviderReply:
        """Append tool results, call the model again, return its reply"""
        print(f"send_tool_result called with: {result}")


### ------------------------
### --- FACTORY FUNCTION ---
### ------------------------

def build_provider(config: dict, tools: list, prompt: str) -> Provider:
    """ Pick a provider based on config file and build it.
    config: dictionary containing config file
    tools: list of tuples for each tool (name, description, input_schema)
    prompt: default system prompt for the model to be activated with
    """
    llm_config = config.get("llm", {})
    provider_name = llm_config.get("provider", "local") # local is default model provider

    if provider_name == "local":
        from mcp_client_console.llm.provider_local import LocalProvider
        return LocalProvider(config, tools, prompt)

    if provider_name == "api":
        from mcp_client_console.llm.provider_api import ApiProvider
        return ApiProvider(config, tools, prompt)

    raise ValueError(f"Unknown llm provider '{provider_name}'")

# llm/langchain_wrapper.py
import json
import logging
from typing import Any, List, Optional, Iterator

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    BaseMessage, AIMessage, HumanMessage, SystemMessage, ToolMessage
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from pydantic import Field, PrivateAttr

from llm.client import AnthropicProxyClient
from tools.langchain_adapter import _get_tool_schema
import re
# Use a logger with higher level to avoid cluttering the console
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)   # Only show warnings and errors


def _parse_pseudo_tool_calls(content: str) -> list:
    """
    Extract tool calls from text like:
    [TOOL_CALL]
    {tool => "http_request", args => { --method "GET" --url "https://..." }}
    [/TOOL_CALL]
    """
    pattern = r"\[TOOL_CALL\]\s*\{tool\s*=>\s*\"([^\"]+)\",\s*args\s*=>\s*\{([^}]+)\}\s*\}\s*\[/TOOL_CALL\]"
    matches = re.findall(pattern, content, re.DOTALL)
    tool_calls = []
    for tool_name, args_str in matches:
        # Parse args like: --method "GET" --url "https://..."
        args = {}
        arg_pattern = r"--(\w+)\s+\"([^\"]*)\""
        for k, v in re.findall(arg_pattern, args_str):
            args[k] = v
        tool_calls.append({
            "id": f"pseudo_{tool_name}_{len(tool_calls)}",
            "name": tool_name,
            "args": args,
            "type": "tool_call",
        })
    return tool_calls

class AnthropicProxyChatModel(BaseChatModel):
    client: AnthropicProxyClient = Field(..., exclude=True)
    model: str = Field(default="claude-sonnet-4-20250514")
    temperature: float = Field(default=0.7)
    max_tokens: int = Field(default=1024)
    _bound_tools: Optional[List[BaseTool]] = PrivateAttr(default=None)

    class Config:
        arbitrary_types_allowed = True

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager=None,
        **kwargs,
    ) -> ChatResult:
        # Convert LangChain messages to the format expected by the proxy
        converted_messages = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                converted_messages.append({"role": "system", "content": msg.content})
            elif isinstance(msg, HumanMessage):
                converted_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                if msg.tool_calls:
                    tool_calls = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["args"]),
                            },
                        }
                        for tc in msg.tool_calls
                    ]
                    converted_messages.append({
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": tool_calls,
                    })
                else:
                    converted_messages.append({"role": "assistant", "content": msg.content})
            elif isinstance(msg, ToolMessage):
                converted_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "name": msg.name,
                    "content": msg.content,
                })
            else:
                raise ValueError(f"Unsupported message type: {type(msg)}")

        # Prepare tools in Anthropic format
        tools = self._bound_tools or kwargs.get("tools")
        anthropic_tools = None
        if tools:
            anthropic_tools = []
            for tool in tools:
                schema = _get_tool_schema(tool)
                anthropic_tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": schema,
                })

        # Log the tools payload only at DEBUG level (won't show by default)
        logger.debug("Anthropic tools:\n%s", json.dumps(anthropic_tools, indent=2))

        response = self.client.chat.completions.create(
        model=self.model,
        messages=converted_messages,
        tools=anthropic_tools,
        tool_choice="auto" if anthropic_tools else None,
        max_tokens=self.max_tokens,
        temperature=self.temperature,
)

        logger.debug("Raw proxy response: %s", response)

        ai_message = response.choices[0].message
        content = ai_message.content or ""

        # Parse tool calls from the response
        lc_tool_calls = []
        if hasattr(ai_message, "tool_calls") and ai_message.tool_calls:
            for tc in ai_message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                lc_tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "args": args,
                    "type": "tool_call",
                })

        if lc_tool_calls:
            message = AIMessage(content=content, tool_calls=lc_tool_calls)
        else:
            message = AIMessage(content=content)
        # If no structured tool calls, try parsing pseudo-calls from content
        if not lc_tool_calls and content:
            pseudo_calls = _parse_pseudo_tool_calls(content)
            if pseudo_calls:
                logger.info("Extracted pseudo tool calls from text: %s", pseudo_calls)
                lc_tool_calls = pseudo_calls
                # Remove the pseudo-call text from the displayed content
                content = re.sub(r"\[TOOL_CALL\].*?\[/TOOL_CALL\]", "", content, flags=re.DOTALL).strip()
        if not content and not lc_tool_calls:
            logger.warning("LLM returned empty response (no content and no tool calls).")

        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager=None,
        **kwargs,
    ) -> Iterator[ChatGeneration]:
        # Fallback to non-streaming
        result = self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        yield result.generations[0]

    def bind_tools(self, tools: List[BaseTool], **kwargs) -> "AnthropicProxyChatModel":
        new_model = self.__class__(
            client=self.client,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        new_model._bound_tools = tools
        return new_model

    @property
    def _llm_type(self) -> str:
        return "anthropic-proxy"
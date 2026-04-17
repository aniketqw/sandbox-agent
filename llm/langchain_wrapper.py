# llm/langchain_wrapper.py
import json
import logging
from typing import Any, List, Optional, Iterator
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from pydantic import Field, PrivateAttr

from llm.client import AnthropicProxyClient
from tools.langchain_adapter import _get_tool_schema

logger = logging.getLogger(__name__)

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
        run_manager = None,
        **kwargs,
    ) -> ChatResult:
        # Convert messages
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

        # Build tools for request
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

        # Prepare request payload for logging
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": converted_messages,
            "temperature": self.temperature,
            "tools": anthropic_tools,
        }
        logger.debug(f"Anthropic request payload: {json.dumps(payload, indent=2)}")

        # Call client
        response = self.client.chat.completions.create(
            model=self.model,
            messages=converted_messages,
            tools=anthropic_tools,
            tool_choice="auto" if anthropic_tools else None,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

        # Handle response
        ai_message = response.choices[0].message
        content = ai_message.content or ""
        lc_tool_calls = []
        if hasattr(ai_message, 'tool_calls') and ai_message.tool_calls:
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

        # Create AIMessage (only include tool_calls if non-empty)
        if lc_tool_calls:
            message = AIMessage(content=content, tool_calls=lc_tool_calls)
        else:
            message = AIMessage(content=content)

        # If both content and tool_calls are empty, log a warning
        if not content and not lc_tool_calls:
            logger.warning("LLM returned empty response (no content and no tool calls).")

        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])

    def _stream(self, *args, **kwargs) -> Iterator[ChatGeneration]:
        result = self._generate(*args, **kwargs)
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
"""
LangChain-compatible wrapper for AnthropicProxyClient.
Supports tool binding and conforms to BaseChatModel interface.
"""

import json
from typing import Any, List, Optional, Iterator, Dict
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from pydantic import Field

from llm_client import AnthropicProxyClient


class AnthropicProxyChatModel(BaseChatModel):
    """
    A LangChain-compatible chat model that uses AnthropicProxyClient.
    """
    client: AnthropicProxyClient = Field(..., exclude=True)
    model: str = Field(default="claude-sonnet-4-20250514")
    temperature: float = Field(default=0.7)
    max_tokens: int = Field(default=1024)

    class Config:
        arbitrary_types_allowed = True

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager = None,
        **kwargs,
    ) -> ChatResult:
        # Convert LangChain messages to the format expected by AnthropicProxyClient
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

        # Extract tools from kwargs if bound
        tools = kwargs.get("tools")
        openai_tools = None
        if tools:
            openai_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.args_schema.schema() if tool.args_schema else {"type": "object", "properties": {}},
                    }
                }
                for tool in tools
            ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=converted_messages,
            tools=openai_tools,
            tool_choice="auto" if openai_tools else None,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

        ai_message = response.choices[0].message
        content = ai_message.content or ""

        # Build LangChain AIMessage with tool calls if present
        lc_tool_calls = []
        if ai_message.tool_calls:
            for tc in ai_message.tool_calls:
                lc_tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "args": json.loads(tc.function.arguments),
                    "type": "tool_call",
                })

        message = AIMessage(content=content, tool_calls=lc_tool_calls if lc_tool_calls else None)
        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager = None,
        **kwargs,
    ) -> Iterator[ChatGeneration]:
        # For simplicity, we don't implement streaming; just yield the full result.
        result = self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        yield result.generations[0]

    def bind_tools(
        self,
        tools: List[BaseTool],
        **kwargs,
    ) -> "AnthropicProxyChatModel":
        """Bind tools to the model for tool calling."""
        return super().bind_tools(tools, **kwargs)

    @property
    def _llm_type(self) -> str:
        return "anthropic-proxy"
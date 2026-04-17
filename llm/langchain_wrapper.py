# llm/langchain_wrapper.py
import json
import logging
import re
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

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)


def _parse_pseudo_tool_calls(content: str) -> list:
    """
    Extract tool calls from various text patterns that LLMs might produce.
    """
    tool_calls = []

    # Pattern 1: [TOOL_CALL]{tool => "name", args => {...}}[/TOOL_CALL]
    pattern1 = r"\[TOOL_CALL\]\s*\{tool\s*=>\s*\"([^\"]+)\",\s*args\s*=>\s*\{([^}]+)\}\s*\}\s*\[/TOOL_CALL\]"
    for tool_name, args_str in re.findall(pattern1, content, re.DOTALL):
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

    # Pattern 2: %tool_name followed by arguments/code
    pattern2 = r"%(\w+)\s+(.*?)(?=\n%|\n\n|$)"
    for tool_name, raw_args in re.findall(pattern2, content, re.DOTALL):
        if tool_name in ["fetch", "http_request"]:
            url_match = re.search(r"(https?://[^\s]+)", raw_args)
            if url_match:
                tool_calls.append({
                    "id": f"pseudo_http_{len(tool_calls)}",
                    "name": "http_request",
                    "args": {"url": url_match.group(1), "method": "GET"},
                    "type": "tool_call",
                })
        elif tool_name == "execute_python":
            code_match = re.search(r"```python\s*(.*?)```", raw_args, re.DOTALL)
            if code_match:
                tool_calls.append({
                    "id": f"pseudo_python_{len(tool_calls)}",
                    "name": "execute_python",
                    "args": {"code": code_match.group(1).strip()},
                    "type": "tool_call",
                })
        elif tool_name == "read_file":
            path_match = re.search(r"([/\w\.-]+)", raw_args)
            if path_match:
                fname = path_match.group(1).replace("/workspace/", "")
                tool_calls.append({
                    "id": f"pseudo_read_{len(tool_calls)}",
                    "name": "read_file",
                    "args": {"filename": fname},
                    "type": "tool_call",
                })

    # Pattern 3: <tool_name>content</tool_name>
    pattern3 = r"<(\w+)>(.*?)</\1>"
    for tool_name, inner in re.findall(pattern3, content, re.DOTALL):
        if tool_name in ["execute_python", "code"]:
            tool_calls.append({
                "id": f"pseudo_python_{len(tool_calls)}",
                "name": "execute_python",
                "args": {"code": inner.strip()},
                "type": "tool_call",
            })
        elif tool_name == "file_read":
            path_match = re.search(r"([/\w\.-]+)", inner)
            if path_match:
                fname = path_match.group(1).replace("/workspace/", "")
                tool_calls.append({
                    "id": f"pseudo_read_{len(tool_calls)}",
                    "name": "read_file",
                    "args": {"filename": fname},
                    "type": "tool_call",
                })

    # Pattern 4: JSON blocks like {"tool": "http_request", "args": {...}}
    pattern4 = r"\{[^{}]*\"tool\"\s*:\s*\"(\w+)\"[^{}]*\"args\"\s*:\s*(\{[^{}]+\})[^{}]*\}"
    for tool_name, args_json in re.findall(pattern4, content):
        try:
            args = json.loads(args_json)
            tool_calls.append({
                "id": f"pseudo_json_{tool_name}_{len(tool_calls)}",
                "name": tool_name,
                "args": args,
                "type": "tool_call",
            })
        except:
            pass

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

        # Parse structured tool calls from the response
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

        # Fallback: try to parse pseudo‑calls from content
        if not lc_tool_calls and content:
            pseudo_calls = _parse_pseudo_tool_calls(content)
            if pseudo_calls:
                logger.info("Extracted pseudo tool calls: %s", pseudo_calls)
                lc_tool_calls = pseudo_calls
                # Clean up the content by removing the pseudo‑syntax
                content = re.sub(r"\[TOOL_CALL\].*?\[/TOOL_CALL\]", "", content, flags=re.DOTALL)
                content = re.sub(r"%\w+.*?(?=\n\n|$)", "", content, flags=re.DOTALL)
                content = re.sub(r"<[^>]+>.*?</[^>]+>", "", content, flags=re.DOTALL)
                content = content.strip()

        if lc_tool_calls:
            message = AIMessage(content=content, tool_calls=lc_tool_calls)
        else:
            message = AIMessage(content=content)

        if not content and not lc_tool_calls:
            logger.warning("LLM returned empty response.")

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
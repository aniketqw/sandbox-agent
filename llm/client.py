# llm/client.py
import json
import requests
from typing import List, Dict, Any, Optional

class AnthropicProxyClient:
    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    class Chat:
        def __init__(self, client):
            self.completions = self.Completions(client)

        class Completions:
            def __init__(self, client):
                self._client = client

            def create(self,
                       model: str,
                       messages: List[Dict[str, Any]],
                       tools: Optional[List[Dict]] = None,
                       tool_choice: Optional[str] = None,
                       max_tokens: int = 1024,
                       temperature: float = 0.7) -> Any:
                # Convert OpenAI messages to Anthropic format
                system_prompt = ""
                anthropic_messages = []

                for msg in messages:
                    role = msg.get("role")
                    content = msg.get("content", "")
                    if role == "system":
                        system_prompt = content
                    elif role == "user":
                        anthropic_messages.append({"role": "user", "content": content})
                    elif role == "assistant":
                        # Handle tool calls in assistant messages
                        if "tool_calls" in msg:
                            tool_calls_content = []
                            for tc in msg["tool_calls"]:
                                tool_calls_content.append({
                                    "type": "tool_use",
                                    "id": tc["id"],
                                    "name": tc["function"]["name"],
                                    "input": json.loads(tc["function"]["arguments"])
                                })
                            anthropic_messages.append({
                                "role": "assistant",
                                "content": tool_calls_content
                            })
                        else:
                            anthropic_messages.append({"role": "assistant", "content": content})
                    elif role == "tool":
                        # Tool response
                        tool_call_id = msg.get("tool_call_id")
                        anthropic_messages.append({
                            "role": "user",
                            "content": [{
                                "type": "tool_result",
                                "tool_use_id": tool_call_id,
                                "content": msg.get("content", "")
                            }]
                        })

                # Convert OpenAI tools to Anthropic tools
                anthropic_tools = None
                if tools:
                    anthropic_tools = []
                    for t in tools:
                        if t.get("type") == "function":
                            func = t["function"]
                            anthropic_tools.append({
                                "name": func["name"],
                                "description": func.get("description", ""),
                                "input_schema": func.get("parameters", {"type": "object", "properties": {}})
                            })

                payload = {
                    "model": self._client.model,
                    "max_tokens": max_tokens,
                    "messages": anthropic_messages,
                    "temperature": temperature,
                }
                if system_prompt:
                    payload["system"] = system_prompt
                            # Inside create() method, after building payload:
                if anthropic_tools:
                    payload["tools"] = anthropic_tools
                    if tool_choice:
                        payload["tool_choice"] = {"type": tool_choice} if isinstance(tool_choice, str) else tool_choice

                headers = {
                    "Content-Type": "application/json",
                    "x-api-key": self._client.api_key,
                    "anthropic-version": "2023-06-01"
                }

                resp = requests.post(f"{self._client.base_url}/v1/messages",
                                     headers=headers,
                                     json=payload)
                resp.raise_for_status()
                data = resp.json()

                # Convert Anthropic response back to OpenAI format for the harness
                return self._convert_response(data)

            def _convert_response(self, data: Dict) -> Any:
                """Convert Anthropic response to an object that mimics OpenAI's response structure."""
                class Choice:
                    def __init__(self, message):
                        self.message = message

                class Response:
                    def __init__(self, choices):
                        self.choices = choices

                # Build assistant message with possible tool calls
                content = ""
                tool_calls = []
                for block in data.get("content", []):
                    if block["type"] == "text":
                        content += block["text"]
                    elif block["type"] == "tool_use":
                        tool_calls.append(
                            ToolCall(
                                id=block["id"],
                                type="function",
                                function=FunctionCall(
                                    name=block["name"],
                                    arguments=json.dumps(block["input"])
                                )
                            )
                        )

                message = Message(content=content, tool_calls=tool_calls)
                choice = Choice(message)
                return Response([choice])

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.chat = self.Chat(self)


# Minimal classes to emulate OpenAI's structure
class FunctionCall:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments

class ToolCall:
    def __init__(self, id, type, function):
        self.id = id
        self.type = type
        self.function = function

class Message:
    def __init__(self, content, tool_calls):
        self.content = content
        self.tool_calls = tool_calls
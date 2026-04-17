# llm/factory.py
"""
LLM factory that returns a LangChain chat model based on environment configuration.
Supports 'opus' (Anthropic proxy) and 'ollama' (local Ollama).
"""

import os
from langchain_core.language_models import BaseChatModel

def get_chat_model() -> BaseChatModel:
    provider = os.getenv("LLM_PROVIDER", "opus").lower()

    if provider == "opus":
        from llm.client import AnthropicProxyClient
        from llm.langchain_wrapper import AnthropicProxyChatModel

        client = AnthropicProxyClient(
            base_url=os.getenv("OPUS_BASE_URL", "https://opus.abhibots.com"),
            api_key=os.getenv("OPUS_API_KEY"),
            model=os.getenv("OPUS_MODEL", "claude-sonnet-4-20250514")
        )
        return AnthropicProxyChatModel(client=client)

    elif provider == "ollama":
        from langchain_ollama import ChatOllama

        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        model = os.getenv("OLLAMA_MODEL", "llama3.2")
        return ChatOllama(
            base_url=base_url,
            model=model,
            temperature=0.7,
        )

    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: {provider}. Use 'opus' or 'ollama'.")
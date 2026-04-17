
# Sandbox Agent Refactoring Documentation

## Overview

This document describes the refactored architecture of the Sandbox Agent, which now uses **LangGraph** for stateful multi‑turn tool execution, **persistent memory** via checkpointing, and **LangSmith** for observability.

## LLM Configuration

The agent supports two LLM backends, selectable via the `LLM_PROVIDER` environment variable:

| Provider | Description | Required Variables |
|----------|-------------|-------------------|
| `ollama` | Local Ollama instance | `OLLAMA_BASE_URL` (default `http://localhost:11434`), `OLLAMA_MODEL` (e.g., `qwen2.5`, `llama3.2`) |
| `opus`   | Anthropic proxy endpoint | `OPUS_BASE_URL`, `OPUS_API_KEY`, `OPUS_MODEL` |

**Switching Providers:**
1. Set `LLM_PROVIDER` in `.env` to either `ollama` or `opus`.
2. Provide the corresponding connection details.
3. Restart the agent.

## Project Structure

```
sandbox-agent/
├── harness.py                 # Main entry point (minimal bootstrapper)
├── agent/                     # LangGraph agent logic
│   ├── __init__.py
│   ├── state.py               # AgentState TypedDict
│   └── graph.py               # StateGraph definition & compilation
├── llm/                       # LLM clients and LangChain wrappers
│   ├── __init__.py
│   ├── factory.py             # LLM factory (selects provider based on env)
│   ├── client.py              # AnthropicProxyClient (custom HTTP client)
│   └── langchain_wrapper.py   # AnthropicProxyChatModel (BaseChatModel)
├── tools/                     # All tool‑related code
│   ├── __init__.py            # Exports TOOL_DISPATCH, TOOLS, get_langchain_tools
│   ├── implementations.py     # Actual tool functions (sandbox interaction)
│   ├── schemas.py             # OpenAI‑style JSON schemas
│   ├── dispatch.py            # TOOL_DISPATCH dictionary
│   └── langchain_adapter.py   # Converts functions → LangChain StructuredTools
├── sandbox/                   # Docker sandbox management
│   ├── __init__.py
│   └── container.py           # start_sandbox, get_container, stop_sandbox
├── tests/                     # Test suite
│   ├── test_all_tools.py      # Comprehensive tool tests
│   └── test_results/          # Log files (generated)
├── agent_workspace/           # Mounted Docker volume (runtime)
├── .env                       # Environment variables (API keys)
└── requirements.txt           # Python dependencies
```

## Module Descriptions

### `harness.py`
The main entry point. It:
- Loads environment variables (`.env`).
- Starts the Docker sandbox.
- Initialises the LangGraph agent graph.
- Runs an interactive REPL loop with streaming output.
- Uses a `thread_id` for persistent memory across turns.
- Displays the active LLM provider and model.

### `agent/`
Contains the LangGraph agent definition.

| File | Purpose |
|------|---------|
| `state.py` | Defines `AgentState`, a TypedDict with `messages` annotated for adding. |
| `graph.py` | Builds the `StateGraph` with `agent` and `tools` nodes, conditional routing, and compiles it with a `MemorySaver` checkpointer. Exports `get_agent_graph()`. Uses `llm.factory.get_chat_model()` to obtain the configured LLM. |

### `llm/`
Handles communication with the LLM provider.

| File | Purpose |
|------|---------|
| `factory.py` | Exports `get_chat_model()` – returns a LangChain `BaseChatModel` based on the `LLM_PROVIDER` environment variable. Supports `"opus"` and `"ollama"`. |
| `client.py` | `AnthropicProxyClient` – a custom client that translates OpenAI‑style requests to Anthropic’s message format for the proxy endpoint. |
| `langchain_wrapper.py` | `AnthropicProxyChatModel` – a LangChain `BaseChatModel` subclass that wraps the proxy client. It enables `.bind_tools()` and integrates with LangGraph. |

### `tools/`
All tool implementations and schemas.

| File | Purpose |
|------|---------|
| `implementations.py` | Contains all tool functions (`run_shell_command`, `execute_python`, `http_request`, `run_playwright_script`, etc.). Each function interacts with the Docker sandbox via `get_container()`. |
| `schemas.py` | OpenAI‑compatible JSON schemas for each tool (used by the LLM to understand parameters). |
| `dispatch.py` | Exports `TOOL_DISPATCH`, a dict mapping tool names to their implementation functions. |
| `langchain_adapter.py` | Dynamically converts the schemas and dispatch table into LangChain `StructuredTool` objects. Exports `get_tools()`. |

### `sandbox/`
Docker container lifecycle management.

| File | Purpose |
|------|---------|
| `container.py` | Functions: `start_sandbox()`, `stop_sandbox()`, `get_container()`. Mounts a host workspace directory, runs the official Playwright Python image, and ensures cleanup via `atexit`. |

### `tests/`
Test suite and logs.

| File | Purpose |
|------|---------|
| `test_all_tools.py` | Comprehensive test script that exercises every tool, verifies HTTP request handling, Playwright automation, package installation, and file exploration utilities. Produces a timestamped log file. |

## Key Functions (by Module)

### `llm.factory`
- `get_chat_model() -> BaseChatModel`: Returns a configured LangChain chat model based on `LLM_PROVIDER`. For `"ollama"` it returns a `ChatOllama` instance; for `"opus"` it returns an `AnthropicProxyChatModel` wrapped around `AnthropicProxyClient`.

### `sandbox.container`
- `start_sandbox()`: Pulls image (if needed), creates/removes stale containers, mounts workspace, returns container object.
- `stop_sandbox()`: Gracefully stops and removes the container.
- `get_container()`: Returns the active container or raises if not started.

### `tools.implementations`
- `run_shell_command(command: str) -> dict`: Executes shell command, returns `stdout`, `stderr`, `exit_code`.
- `execute_python(code: str) -> dict`: Writes code to a temp file and runs it.
- `write_file(filename: str, content: str) -> dict`: Saves text file to `/workspace`.
- `read_file(filename: str) -> dict`: Reads file content.
- `http_request(url: str, method: str = "GET", data: str = None, headers: dict = None) -> dict`: Performs HTTP request; large bodies are saved to file with a summary returned.
- `install_python_package(packages: list) -> dict`: Installs pip packages, verifies import.
- `run_playwright_script(script: str) -> dict`: Executes Playwright automation script (Chromium pre‑installed).
- `grep_file(filepath: str, pattern: str, max_lines: int = 50) -> dict`: Searches file with regex.
- `read_file_range(filepath: str, start_line: int = 1, end_line: int = 100) -> dict`: Reads specific line range.
- `list_files(directory: str = "/workspace") -> dict`: Lists directory contents.

### `llm.client`
- `AnthropicProxyClient(base_url, api_key, model)`: Constructor.
- `client.chat.completions.create(...)`: Sends request to proxy, returns OpenAI‑shaped response.

### `llm.langchain_wrapper`
- `AnthropicProxyChatModel`: Implements `_generate()` and `bind_tools()`.

### `agent.graph`
- `get_agent_graph()`: Returns a compiled LangGraph `StateGraph` with `MemorySaver` checkpointing. Uses `get_chat_model()` from `llm.factory`.

### `harness`
- `main()`: Orchestrates the REPL loop, streams agent events, and prints final responses.

## Environment Variables (`.env`)

| Variable | Description |
|----------|-------------|
| `LLM_PROVIDER` | Which LLM backend to use: `"ollama"` or `"opus"` (default: `"opus"`). |
| `OPUS_BASE_URL` | (Opus only) Base URL of the Anthropic proxy (default: `https://opus.abhibots.com`). |
| `OPUS_API_KEY` | (Opus only) **Required** – API key for the proxy. |
| `OPUS_MODEL` | (Opus only) Model name (default: `claude-sonnet-4-20250514`). |
| `OLLAMA_BASE_URL` | (Ollama only) Ollama server URL (default: `http://localhost:11434`). |
| `OLLAMA_MODEL` | (Ollama only) Model name (e.g., `llama3.2`, `qwen2.5`). |
| `LANGSMITH_API_KEY` | (Optional) LangSmith API key for tracing. |
| `LANGSMITH_PROJECT` | (Optional) LangSmith project name (default: `sandbox-agent`). |

## Running the Agent

```bash
# Install dependencies
pip install -r requirements.txt

# Set up .env file with API keys and LLM_PROVIDER

# Run the interactive agent
python harness.py

# Run the test suite
python tests/test_all_tools.py
```

## Architectural Benefits

- **Multi‑turn tool calling**: LangGraph automatically loops until the task is complete.
- **Persistent memory**: `thread_id` ensures conversation history is retained across user inputs.
- **Observability**: LangSmith traces every LLM call and tool execution.
- **Separation of concerns**: Clear boundaries between sandbox, tools, LLM, and agent logic.
- **Extensibility**: Adding a new tool only requires updating `tools/implementations.py`, `tools/schemas.py`, and `tools/dispatch.py`; the LangChain adapter picks it up automatically.
- **Multi‑LLM support**: Switch between local Ollama and cloud‑based proxies via a single environment variable.

## Future Enhancements

- Add streaming token‑by‑token output.
- Implement human‑in‑the‑loop approval for sensitive operations.
- Replace in‑memory checkpointing with a persistent database (e.g., Postgres, Redis).
- Add a web UI using FastAPI/Streamlit.

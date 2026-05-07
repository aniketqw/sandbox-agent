# sandbox-agent — Claude Code Guide

## What this project is
A LangGraph-based AI agent that runs code inside a Docker sandbox. The agent can search the web, execute Python/shell commands, automate browsers with Playwright, and interact with the user. It also connects to the user's Educative.io account to load and use course content.

## How to run
```bash
conda activate sandbox-agent
python harness.py           # interactive REPL (default: Anthropic proxy)
LLM_PROVIDER=ollama python harness.py   # use local Ollama instead
```
Requires Docker running and the `sandbox-agent:latest` image built.

## IMPORTANT — always use the conda environment
All Python commands in this project **must** run inside the `sandbox-agent` conda env.
- In Claude Code sessions: use `conda run -n sandbox-agent <command>` for every Bash/Python call.
- Never use the system Python or any other env — dependencies (docker, langgraph, playwright, …) are only installed in `sandbox-agent`.

## Sub-agent pattern (see subagent.md)
The main graph (`agent/graph.py`) spawns focused ReAct sub-agents via `agent/workers.py`.
- Use `create_coder_agent(tools=[...])` for code-execution subtasks.
- Sub-agents share the same `AgentState` shape (`messages`, `step_count`).
- In LangGraph Studio all side-effects (Docker, browser) are mocked automatically.

## Project layout
```
agent/          LangGraph graph, state, and worker definitions
llm/            LLM client factory (Anthropic proxy or Ollama)
tools/          All tool schemas, implementations, and dispatch table
  schemas.py          OpenAI-compatible JSON schemas sent to the LLM
  implementations.py  Core tool functions (shell, Python, file I/O, HTTP, Playwright, human)
  educative_tool.py   Educative.io browser + course scraper tools
  dispatch.py         Maps tool names → functions
  langchain_adapter.py  Converts schemas to LangChain StructuredTools
sandbox/        Docker container lifecycle management
agent_workspace/ Shared volume between host and container (/workspace inside Docker)
harness.py      Main entry point — Rich REPL
```

## Tools available to the agent
| Tool | Purpose |
|------|---------|
| `run_shell_command` | Run any shell command in the Docker sandbox |
| `execute_python` | Write + run Python inside the sandbox |
| `write_file` / `read_file` | File I/O in /workspace |
| `grep_file` / `read_file_range` / `list_files` | File inspection |
| `http_request` | GET/POST with fallback to curl |
| `install_python_package` | pip install inside sandbox |
| `run_playwright_script` | Headless browser automation (sandbox) |
| `web_search` | Tavily-powered web search |
| `ask_human` | Ask the user a question |
| `request_approval` | Gate multi-step plans behind user approval |
| `open_educative_course` | Open Chrome (headful) with Educative auth, scrape course |
| `load_educative_course` | Load a previously saved course JSON |
| `list_educative_courses` | List all saved courses |

## Adding a new tool
1. Write the implementation function in `tools/implementations.py` (or a new file like `tools/educative_tool.py`)
2. Add the OpenAI-compatible schema to the `TOOLS` list in `tools/schemas.py`
3. Add the mapping `"tool_name": function` to `TOOL_DISPATCH` in `tools/dispatch.py`
4. All three lists are read automatically by `tools/__init__.py` and `tools/langchain_adapter.py`

## Environment variables
| Var | Purpose |
|-----|---------|
| `OPUS_API_KEY` | Anthropic proxy key |
| `TAVILY_API_KEY` | Web search |
| `LANGSMITH_API_KEY` | LangSmith tracing |
| `LLM_PROVIDER` | `anthropic` (default) or `ollama` |
| `SANDBOX_PERSISTENT` | `true` keeps the Docker container alive between runs |

## Key behaviours
- The agent graph has a max of 15 steps and 3 error retries (reflection node).
- In LangGraph Studio, all tools degrade gracefully to mock responses (no Docker, no browser).
- Tools that run code (shell, Python, Playwright) execute inside the container, not on the host.
- `open_educative_course` is the exception — it launches Chrome **on the host** (headful).
- Courses scraped by `open_educative_course` are saved to `agent_workspace/educative_courses/`.

## Playwright setup (host vs Docker)
- **Docker container**: Playwright is pre-installed in `Dockerfile.sandbox`. Used by `run_playwright_script` (headless).
- **Host (macOS)**: Playwright must be installed in the `sandbox-agent` conda env for `open_educative_course`:
  ```bash
  pip install playwright
  playwright install chrome
  ```
  This is a one-time setup. `open_educative_course` uses `sys.executable` to spawn the browser script on the host, so it needs the conda env to have playwright.

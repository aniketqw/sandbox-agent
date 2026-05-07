# Project Info

## Purpose
A local AI agent sandbox for learning and building with LangGraph. The agent can execute
code, browse the web, automate browsers, and now load content from Educative.io courses
to help build things guided by course material.

## Educative.io Integration

### How it works
`tools/educative_tool.py` holds 41 auth cookies exported from an active Educative session.
When called, it:
1. Decodes the base64 cookie blob into individual cookie objects
2. Launches Chrome **on the host Mac** (headful, visible) via Playwright
3. Injects all cookies so the browser is immediately logged in
4. Navigates to the requested course URL
5. Scrapes the course structure (title, lesson list, current page text)
6. Saves JSON to `agent_workspace/educative_courses/<slug>.json`
7. Returns a summary to the agent; the browser stays open for the user to follow along

### Key cookies used for auth
| Cookie | Role |
|--------|------|
| `flask-auth` | Primary session auth token |
| `flask-session` | Flask session cookie |
| `magicbox-auth` | Secondary auth token |
| `cache_token` | API cache token |
| `logged_in` | `true` — signals active session |
| `subscribed` | `true` — signals active subscription |

### Cookie expiry
The `flask-session` expires ~2026-05-14. After that, export fresh cookies from your browser
(Cookie Editor extension → Export as JSON base64) and update `_EDUCATIVE_COOKIES_B64`
in `tools/educative_tool.py`.

### Saved course location
- Host path: `agent_workspace/educative_courses/`
- Inside sandbox: `/workspace/educative_courses/`
- Format: JSON with keys `title`, `description`, `url`, `lessons` (list of `{title, url}`)

### First-time setup
```bash
pip install playwright
playwright install chrome
```

## Dependencies
```
langgraph, langchain, langchain-core, langchain-ollama
langsmith, pydantic, requests, python-dotenv
docker, rich, tavily-python, playwright
langgraph-cli
```

## Docker sandbox image
Built from `Dockerfile.sandbox`. Contains Python 3.12, Playwright + Chromium, requests,
beautifulsoup4, pandas, tavily-python. Rebuild with:
```bash
docker build -f Dockerfile.sandbox -t sandbox-agent:latest .
```

## LLM providers
| Provider | How to activate |
|----------|----------------|
| Anthropic proxy | Default. Set `OPUS_API_KEY`. |
| Ollama (local) | `LLM_PROVIDER=ollama python harness.py` |

## Courses currently saved
Run `list_educative_courses` tool (or check `agent_workspace/educative_courses/`) to see
what has been scraped so far.

## Typical workflow with a course
```
You: "Open the LangGraph course and help me understand checkpointing"

Agent:
  1. open_educative_course(url="https://www.educative.io/courses/langgraph.../checkpointing")
     → Chrome opens, course scraped, lessons listed
  2. ask_human("Do you want me to build a working checkpointing example?")
  3. You: "Yes, using SQLite"
  4. write_file + execute_python → builds and runs the example in sandbox
  5. Returns the result + explanation grounded in course content
```

## File structure
```
sandbox-agent/
├── CLAUDE.md              Claude Code guide (tools, layout, env vars)
├── subagent.md            Sub-agent and worker patterns
├── info.md                This file — project overview and integrations
├── harness.py             Interactive REPL entry point
├── agent/
│   ├── graph.py           LangGraph state machine
│   ├── state.py           AgentState TypedDict
│   └── workers.py         ReAct sub-agent factory
├── tools/
│   ├── schemas.py         LLM tool schemas (OpenAI format)
│   ├── implementations.py Core tool functions
│   ├── educative_tool.py  Educative.io browser + course tools  ← NEW
│   ├── dispatch.py        Tool name → function mapping
│   └── langchain_adapter.py  Converts to LangChain StructuredTools
├── llm/
│   ├── client.py          Anthropic proxy client
│   ├── factory.py         Returns correct LLM based on LLM_PROVIDER
│   └── langchain_wrapper.py  LangChain-compatible wrapper
├── sandbox/
│   └── container.py       Docker container lifecycle
├── agent_workspace/        Shared volume (host ↔ container)
│   └── educative_courses/  Scraped course JSONs  ← NEW
└── langgraph.json         LangGraph deployment config
```

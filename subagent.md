# Sub-agent & Worker Patterns

There are **two sub-agent patterns** in this project:
1. **Claude Code parallel sub-agents** — edit files in parallel during development
2. **LangGraph ReAct sub-agents** — execute at runtime inside the agent graph

---

## Claude Code parallel sub-agents (file-editing pattern)

Use this pattern when a task touches **multiple independent file groups** and edits can happen concurrently.

### File ownership table

| Sub-agent | Owns | Example task |
|-----------|------|-------------|
| tools-agent | `tools/` | Add new tool: schema + implementation + dispatch entry |
| agent-agent | `agent/` | Update graph edges or state shape |
| llm-agent | `llm/` | Swap LLM provider or add streaming |
| config-agent | `CLAUDE.md`, `requirements.txt`, `langgraph.json` | Update docs/dependencies |

### When to use

- Adding a feature that spans `tools/` + `agent/` (e.g., new tool + graph wiring)
- Refactoring that touches 3+ files across different directories
- **NOT** for changes within a single file — just edit directly

### How to invoke (in Claude Code)

Send a single message with multiple `Agent(...)` tool calls — they execute concurrently:

```python
# Example: Adding a new tool that requires updates in 3 places

# Agent 1: Add schema + implementation
Agent({
  "description": "Add new_tool to schemas and implementations",
  "prompt": "Edit tools/schemas.py and tools/implementations.py: add new_tool definition..."
})

# Agent 2: Update dispatch
Agent({
  "description": "Wire new_tool into dispatch",
  "prompt": "Edit tools/dispatch.py: add 'new_tool': new_tool_func to TOOL_DISPATCH..."
})

# Agent 3: Update docs
Agent({
  "description": "Document new_tool in CLAUDE.md",
  "prompt": "Edit CLAUDE.md: add new_tool row to the Tools table..."
})
```

Each agent runs independently on a copy of the repo (via `isolation: "worktree"`). Changes are merged back afterward.

### Distinction from LangGraph sub-agents

- **Claude Code sub-agents** (file editing): run in parallel during development, isolated worktrees
- **LangGraph ReAct sub-agents** (runtime workers): execute at runtime inside the agent graph, share the 15-step budget and tool calls

---

## LangGraph ReAct sub-agents (runtime workers)

`agent/workers.py` builds **ReAct sub-agents** — smaller LangGraph agents with their own
tool subset, spun up by the main agent for focused subtasks (e.g., writing and testing code
without using the full tool list).

## How the main graph works
```
user input
    │
    ▼
agent_node  ──── LLM decides which tool to call
    │
    ├── (tool call) ──► tools node ──► back to agent_node
    │
    ├── (error) ──────► reflect node ──► back to agent_node  (max 3 retries)
    │
    └── (no tool / END) ──► return to user
```
Max 15 steps total. Defined in `agent/graph.py`.

## Creating a sub-agent worker
```python
# agent/workers.py
from agent.workers import create_coder_agent

coder = create_coder_agent(tools=[execute_python, write_file, read_file])
result = coder.invoke({"messages": [HumanMessage(content="write a fibonacci function")]})
```
`create_coder_agent` returns a compiled LangGraph graph with a ReAct loop.

## Educative course sub-agent pattern
When the user loads a course, the recommended pattern is:

1. Main agent calls `open_educative_course(url=...)` → gets lesson list
2. Main agent calls `ask_human("What do you want to do with this course?")` → gets task
3. Main agent can then:
   - Spin up a coder sub-agent to implement concepts from the lesson
   - Call `load_educative_course(filename=...)` to feed full lesson text as context
   - Use `web_search` to supplement with external examples
   - Use `write_file` + `execute_python` to build and test code from the course

## Passing course content to the LLM
Course data saved in `agent_workspace/educative_courses/` is accessible inside the sandbox
at `/workspace/educative_courses/`. The agent can:
```
read_file("educative_courses/courses_langgraph_why-langgraph-exists.json")
```
and include the lesson text in its reasoning context.

## State shape
```python
# agent/state.py
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    step_count: int
```
Sub-agents share the same state shape.

## LangGraph Studio
When running inside LangGraph Studio (`LANGGRAPH_API_URL` is set), all tool calls that
require Docker or a browser return mock responses. The graph and sub-agent logic still
execute normally — only side effects are suppressed.

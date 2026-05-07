# Using the Educative Tool Pattern

## Quick start

```python
# In harness.py, the agent has access to these tools:
# - open_educative_course(url: str)  — Opens course in headful Chrome on host, scrapes structure
# - load_educative_course(filename: str)  — Loads previously scraped course JSON
# - list_educative_courses()  — Lists all saved courses in agent_workspace/educative_courses/
```

## Tool setup checklist

### Prerequisites
- `sandbox-agent` conda env with playwright installed:
  ```bash
  conda run -n sandbox-agent pip install playwright
  conda run -n sandbox-agent playwright install chrome
  ```
- Docker container running with `sandbox-agent:latest` image

### Tool availability
✓ Educative tools are registered in `tools/dispatch.py` lines 16-20  
✓ Educative tools are converted to LangChain tools in `tools/langchain_adapter.py`  
✓ Educative tools are bound to the LLM in `agent/graph.py` line 33 via `.bind_tools()`  
✓ All 3 tools are available via `from tools.langchain_adapter import get_tools()`

## When the agent should call the tool

The agent **automatically chooses** to call `open_educative_course` when you ask it to use a course:
```
You: "Use this course: https://www.educative.io/courses/langgraph-from-langchain-user-to-agent-builder/why-langgraph-exists"

Agent:
  1. Calls open_educative_course(url=...) 
  2. Chrome opens on host (headful) with your Educative session injected via cookies
  3. Tool scrapes course structure (title, lessons, content)
  4. Saves JSON to agent_workspace/educative_courses/<slug>.json
  5. Returns summary to agent for next steps
```

## Improved error recovery

If `open_educative_course` fails, the **reflect_node** now:
1. **Detects the error type** (tool bug vs. wrong argument)
2. **Provides smart guidance** — if it's a tool-side bug, LLM tries a different approach; if it's bad arguments, LLM fixes them
3. **Persists correction history** — the conversation remembers what was tried and what failed

## If the tool fails

### Issue: ModuleNotFoundError: No module named 'playwright'
**Root cause:** Playwright not installed in host conda env (not Docker).
**Fix:** 
```bash
conda run -n sandbox-agent pip install playwright
conda run -n sandbox-agent playwright install chrome
```

### Issue: Chrome timeout / content extraction failed
**Root cause:** Browser hangs or Educative cookies expired.
**Fix:** 
1. Check LangSmith logs for the exact error in the temp script (`/var/folders/.../educ_XXXXX.py`)
2. Update cookies in `tools/educative_tool.py` line 10 if expired (see `info.md`)

### Issue: Agent doesn't call the tool
**Likelihood:** Agent chose a different approach (e.g., manual scripting).
**Fix (using subagent pattern from subagent.md):**

Use parallel Claude Code sub-agents to split the work:
```
Agent 1 (tools-agent):
  - Review tools/educative_tool.py for issues
  - Check tools/dispatch.py registration
  - Verify schemas in tools/schemas.py

Agent 2 (config-agent):
  - Update CLAUDE.md with better guidance
  - Ensure playwright in requirements.txt
  - Document the fix

Agent 3 (harness-agent):
  - Re-run python harness.py
  - Test the tool with the course URL
  - Report success/failure
```

This approach parallelizes debugging and fixes across independent file groups (as documented in subagent.md).

## Integration with LangGraph ReAct workers

After `open_educative_course` loads a course, the main agent can:

1. Call `ask_human("What do you want to build from this course?")`
2. Spawn a **coder sub-agent** (via `create_coder_agent` in `agent/workers.py`):
   ```python
   coder = create_coder_agent(tools=[execute_python, write_file, read_file])
   coder.invoke({
     "messages": [
       HumanMessage(content=f"Build a working example of checkpointing from: {course_content}")
     ]
   })
   ```
3. The sub-agent implements, tests, and returns the code

See `subagent.md` for full patterns.

## Cookie expiry & maintenance

Educative cookies in `tools/educative_tool.py:10` expire ~2026-05-14.

When expired, export fresh cookies:
1. Open https://www.educative.io in your browser
2. Install "Cookie Editor" extension
3. Export cookies as JSON (base64)
4. Update `_EDUCATIVE_COOKIES_B64` in `tools/educative_tool.py`

This is a **config-agent** task in the subagent pattern.

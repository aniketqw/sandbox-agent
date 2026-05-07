# Debugging Guide — Using Parallel Sub-agents

This guide documents how to debug and fix multi-file issues in sandbox-agent using the **Claude Code parallel sub-agent pattern** from `subagent.md`.

## Recent fixes applied (2026-05-07)

### Bug 1: Educative tool cookie encoding error

**What happened**: `open_educative_course` tool failed with `NameError: name 'true' is not defined`

**Root cause**: Cookies were embedded into a Python temp script using `json.dumps()`, which produces JSON booleans (`true`/`false`) — not valid Python (`True`/`False`).

```python
# BEFORE (line 395 in tools/educative_tool.py)
cookies=json.dumps(pw_cookies),  # produces: [{"secure": true}, ...] ❌ Python NameError

# AFTER  
cookies=repr(pw_cookies),        # produces: [{"secure": True}, ...] ✅ Valid Python
```

**Why this matters**: Any tool that embeds dynamic data into code (shell, Python, Playwright scripts) needs to use `repr()` for Python literals, `json.dumps()` for JSON-safe strings, not the other way around.

### Bug 2: Reflect node not handling tool bugs properly

**What happened**: When `open_educative_course` failed, the reflect_node sent a generic correction prompt. The LLM saw a tool failure (not an LLM mistake) but was guided to "fix your tool call" — which made no sense.

**Root cause**: 
1. `_has_error()` used broad substring matching (`"error"`, `"Error"`), causing false positives
2. `reflect_node` didn't distinguish between **LLM mistakes** ("wrong arguments") vs **tool bugs** ("internal exception")
3. Correction prompt was not persisted to history

**Fixes applied**:

```python
# BEFORE: fragile error detection
def _has_error(content: str) -> bool:
    error_markers = ["Error", "error", "Traceback", "NameError", ...]
    return any(marker in content for marker in error_markers)
    # ❌ "error" appears in normal logs, false positives

# AFTER: JSON-first, specific exception names
def _has_error(content: str) -> bool:
    try:
        if _json.loads(content).get("success") is False:
            return True
    except:
        pass
    error_markers = ["Traceback", "NameError", "TypeError", "ImportError", ...]
    # ✅ structured JSON + specific exception class names only
```

```python
# BEFORE: generic correction prompt
correction_prompt = HumanMessage(content=(
    f"[REFLECTION] {error_detail[:500]}\n\n"
    "Common fixes:\n- Use exact file paths\n- Do NOT reference undefined variables\n..."
))
response = llm_with_tools.invoke(messages + [correction_prompt])
return {"messages": [response]}  # ❌ prompt ephemeral, not saved

# AFTER: smart classification + persistence  
is_tool_bug = any(marker in error_detail for marker in ["Traceback", "NameError", ...])
if is_tool_bug:
    guidance = "Fix the Python code / use a different approach"
else:
    guidance = "Use correct file paths / valid arguments"
    
correction_prompt = HumanMessage(content=f"[REFLECTION – attempt 1/3] {guidance}")
response = llm_with_tools.invoke(messages + [correction_prompt])
return {
    "messages": [correction_prompt, response],  # ✅ both saved to history
    "correction_prompt": correction_prompt.content,
}
```

---

## How to apply similar multi-file fixes

### Pattern: Use parallel Claude sub-agents

When a bug affects multiple independent file groups, spawn agents in parallel:

**Example: Fix a new tool's broken implementation**

```python
# In Claude Code, send ONE message with multiple Agent(...) calls:

Agent({
  "description": "Fix tool implementation",
  "prompt": "tools/my_tool.py has a bug in line 42. Review the function and fix it..."
  # OR use isolation: "worktree" to edit in parallel
})

Agent({
  "description": "Update tool registration",
  "prompt": "Update tools/dispatch.py to register the fixed tool..."
})

Agent({
  "description": "Update docs",
  "prompt": "Update CLAUDE.md to document the fixed tool..."
})
```

All three agents run **in parallel** on independent copies (worktrees), then results are merged.

### File ownership for this project

| Agent | Owns | Task examples |
|-------|------|---|
| **tools-agent** | `tools/` | Debug tool implementation, fix schemas, update dispatch |
| **agent-agent** | `agent/` | Fix graph logic, improve reflect_node, update state |
| **llm-agent** | `llm/` | Swap LLM provider, add streaming, tune parameters |
| **config-agent** | `CLAUDE.md`, `requirements.txt`, `langgraph.json` | Docs, deps, deployment config |

---

## Debugging workflow for future issues

### Step 1: Reproduce the bug
- Check LangSmith logs for the exact error trace
- Identify **where** it fails (which tool, which line, which file)

### Step 2: Classify the bug
| Type | Where | How to fix | Example |
|------|-------|-----------|---------|
| **Data encoding** | tools/ | Wrong json.dumps vs repr vs str | `json.dumps(pw_cookies)` → `repr(pw_cookies)` |
| **Graph logic** | agent/ | Wrong edge logic, missing state field | reflect_node not persisting correction |
| **Tool registration** | tools/dispatch.py, tools/schemas.py | Missing mapping, wrong schema | new_tool not in TOOL_DISPATCH |
| **LLM behavior** | llm/ | Wrong model, wrong prompt, missing context | model doesn't call expected tool |

### Step 3: Spawn parallel agents
- Split by file group (tools-agent, agent-agent, etc.)
- One agent per independent directory
- Each agent makes its own edits, runs tests, reports success

### Step 4: Merge & verify
- Verify in `python harness.py` that the tool works end-to-end
- Update memory/docs for future sessions

---

## Key lessons

1. **Data embedding**: Use `repr()` for Python code, `json.dumps()` for JSON/APIs, raw strings carefully
2. **Error detection**: Exact exception class names > substring matching (avoid false positives)
3. **Correction strategy**: Distinguish between "LLM error" (wrong arguments) and "tool error" (implementation bug)
4. **State persistence**: Correction prompts should be saved to message history so future turns understand what was tried
5. **Parallel debugging**: Multi-file issues are faster with agents split by file group

See `subagent.md` for the full Claude Code parallel sub-agent pattern.

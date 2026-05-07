# agent/graph.py
import os
import json as _json
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import SystemMessage, ToolMessage, HumanMessage, AIMessage

from sandbox.container import ensure_sandbox
from llm.factory import get_chat_model
from tools.langchain_adapter import get_tools
from agent.state import AgentState

MAX_STEPS = 15
MAX_RETRIES = 3

_graph = None
_checkpointer = None


def _has_error(content: str) -> bool:
    # Check for explicit {"success": false} JSON response first
    try:
        parsed = _json.loads(content)
        if isinstance(parsed, dict) and parsed.get("success") is False:
            return True
    except (_json.JSONDecodeError, TypeError):
        pass
    # Fall back to specific exception class names only (avoids false positives on "error" substring)
    error_markers = [
        "Traceback",
        "NameError",
        "TypeError",
        "ValueError",
        "AttributeError",
        "ImportError",
        "SyntaxError",
        "IndexError",
        "KeyError",
        "RuntimeError",
        "CancelledError",
        "Exception:",
    ]
    return any(marker in content for marker in error_markers)


def get_agent_graph():
    global _graph, _checkpointer
    if _graph is not None:
        return _graph, _checkpointer

    llm = get_chat_model()
    tools = get_tools()
    tool_node = ToolNode(tools)
    llm_with_tools = llm.bind_tools(tools)

    def agent_node(state: AgentState):
        ensure_sandbox()   # Idempotent: ensures container is running
        messages = state["messages"]
        response = llm_with_tools.invoke(messages)
        return {
            "messages": [response],
            "step_count": state.get("step_count", 0) + 1,
            "retry_count": state.get("retry_count", 0),
        }

    def reflect_node(state: AgentState):
        messages = state["messages"]

        # Find the last ToolMessage to extract error detail
        last_tool_msg = None
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage):
                last_tool_msg = msg
                break

        error_detail = last_tool_msg.content if last_tool_msg else "Unknown error"
        error_snippet = error_detail[:600]

        # Detect whether this looks like a tool/code bug vs a wrong-argument mistake
        tool_bug_markers = [
            "Traceback",
            "NameError",
            "TypeError",
            "ValueError",
            "AttributeError",
            "ImportError",
            "SyntaxError",
            "IndexError",
            "KeyError",
            "RuntimeError",
        ]
        is_tool_bug = any(marker in error_detail for marker in tool_bug_markers)

        if is_tool_bug:
            guidance = (
                "This looks like a CODE or TOOL BUG. Please:\n"
                "1. Read the full traceback carefully.\n"
                "2. Fix the Python code before retrying (check variable names, imports, and logic).\n"
                "3. Do NOT repeat the same code unchanged.\n"
                "4. If the bug is inside an imported helper, work around it inline.\n"
            )
        else:
            guidance = (
                "This looks like a WRONG ARGUMENT or MISSING DATA issue. Please:\n"
                "1. Use the exact file path returned by a prior tool call (e.g. http_request).\n"
                "2. Do NOT reference variables that were never defined.\n"
                "3. Save data to a file first, then read it back before processing.\n"
                "4. Ensure the 'code' argument to execute_python is a complete, valid Python script.\n"
            )

        correction_prompt = HumanMessage(content=(
            f"[REFLECTION – attempt {state.get('retry_count', 0) + 1}/{MAX_RETRIES}] "
            f"The previous tool call failed with:\n{error_snippet}\n\n"
            f"{guidance}"
            "Provide a CORRECTED tool call now."
        ))

        response = llm_with_tools.invoke(messages + [correction_prompt])
        return {
            "messages": [correction_prompt, response],
            "step_count": state.get("step_count", 0) + 1,
            "retry_count": state.get("retry_count", 0) + 1,
            "correction_prompt": correction_prompt.content,
        }

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    workflow.add_node("reflect", reflect_node)
    workflow.set_entry_point("agent")

    def after_agent(state: AgentState):
        if state.get("step_count", 0) >= MAX_STEPS:
            return END
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "tools"
        return END

    def after_tools(state: AgentState):
        last_msg = state["messages"][-1]
        if isinstance(last_msg, ToolMessage) and _has_error(last_msg.content):
            if state.get("retry_count", 0) < MAX_RETRIES:
                return "reflect"
            else:
                return END
        return "agent"

    workflow.add_conditional_edges("agent", after_agent, {"tools": "tools", END: END})
    workflow.add_conditional_edges("tools", after_tools, {"reflect": "reflect", "agent": "agent", END: END})
    workflow.add_edge("reflect", "agent")

    _checkpointer = MemorySaver()
    _graph = workflow.compile(checkpointer=_checkpointer)
    return _graph, _checkpointer


def get_graph():
    graph, _ = get_agent_graph()
    return graph
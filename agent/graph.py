# agent/graph.py
import os
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
    error_markers = ["Error", "error", "Traceback", "NameError", "TypeError", "undefined", "CancelledError"]
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
        last_tool_msg = None
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage):
                last_tool_msg = msg
                break

        error_detail = last_tool_msg.content if last_tool_msg else "Unknown error"
        correction_prompt = HumanMessage(content=(
            f"[REFLECTION] The previous tool call failed with:\n{error_detail[:500]}\n\n"
            "Please analyze the error and provide a CORRECTED tool call. "
            "Common fixes:\n"
            "- Use the exact file path returned by http_request.\n"
            "- Do NOT reference undefined variables.\n"
            "- Save data to a file first, then read it back.\n"
            "- For execute_python, ensure the 'code' argument is a valid Python script."
        ))
        response = llm_with_tools.invoke(messages + [correction_prompt])
        return {
            "messages": [response],
            "step_count": state.get("step_count", 0) + 1,
            "retry_count": state.get("retry_count", 0) + 1,
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
# agent/graph.py
import os
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import SystemMessage, ToolMessage, HumanMessage

from sandbox.container import start_sandbox, _container
from llm.factory import get_chat_model
from tools.langchain_adapter import get_tools
from agent.state import AgentState

MAX_STEPS = 15

_graph = None
_checkpointer = None


def ensure_sandbox():
    """Start sandbox if not already running."""
    if _container is None:
        print("[Graph] Starting sandbox container...")
        start_sandbox()


def get_agent_graph():
    global _graph, _checkpointer
    if _graph is not None:
        return _graph, _checkpointer

    llm = get_chat_model()
    tools = get_tools()
    tool_node = ToolNode(tools)
    llm_with_tools = llm.bind_tools(tools)

    def agent_node(state: AgentState):
        ensure_sandbox()
        messages = state["messages"]

        # If the last message is a tool result, add a continuation reminder
        if messages and isinstance(messages[-1], ToolMessage):
            content = messages[-1].content
            # Inject specific hints for common errors
            if "TypeError: string indices must be integers" in content:
                hint = HumanMessage(
                    content="[SYSTEM HINT] The JSON file contains the raw data directly (an array). "
                            "Use `data = json.load(f)` and then iterate over `data`."
                )
                messages = messages + [hint]
            elif "NameError: name 'null' is not defined" in content:
                hint = HumanMessage(
                    content="[SYSTEM HINT] There was a Python syntax error. "
                            "Check that all variables are defined and JSON is parsed correctly."
                )
                messages = messages + [hint]
            else:
                reminder = HumanMessage(
                    content="[SYSTEM] Tool executed. Continue with the next step of the plan."
                )
                messages = messages + [reminder]

        system = SystemMessage(
            content="You MUST complete all steps of the user's request. Do not stop until the task is fully done."
        )
        response = llm_with_tools.invoke([system] + messages)
        return {
            "messages": [response],
            "step_count": state.get("step_count", 0) + 1,
        }

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    workflow.set_entry_point("agent")

    def after_agent(state: AgentState):
        if state.get("step_count", 0) >= MAX_STEPS:
            return END
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "tools"
        return END

    workflow.add_conditional_edges("agent", after_agent, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")

    _checkpointer = MemorySaver()
    _graph = workflow.compile(checkpointer=_checkpointer)
    return _graph, _checkpointer


def get_graph():
    """Get the compiled graph for LangGraph Studio."""
    graph, _ = get_agent_graph()
    return graph
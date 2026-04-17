# agent/graph.py (updated)
import os
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from llm.factory import get_chat_model
from tools.langchain_adapter import get_tools
from agent.state import AgentState

MAX_STEPS = 10   # safety limit

_graph = None
_checkpointer = None

def get_agent_graph():
    global _graph, _checkpointer
    if _graph is not None:
        return _graph, _checkpointer

    llm = get_chat_model()
    tools = get_tools()
    llm_with_tools = llm.bind_tools(tools)

    def agent_node(state: AgentState):
        response = llm_with_tools.invoke(state["messages"])
        return {
            "messages": [response],
            "step_count": state.get("step_count", 0) + 1
        }

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", ToolNode(tools))
    workflow.set_entry_point("agent")

    def should_continue(state: AgentState):
        if state.get("step_count", 0) >= MAX_STEPS:
            return END
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    workflow.add_conditional_edges("agent", should_continue)
    workflow.add_edge("tools", "agent")

    _checkpointer = MemorySaver()
    _graph = workflow.compile(checkpointer=_checkpointer)
    return _graph, _checkpointer
"""
LangGraph agent graph definition.
Uses a custom state machine with agent node and tools node.
Includes persistent memory via MemorySaver.
"""

from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from langchain_tools import get_tools
from langchain_llm import AnthropicProxyChatModel
from llm_client import AnthropicProxyClient
import os

# Define state
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]

# Singleton graph instance
_graph = None
_checkpointer = None

def get_agent_graph():
    global _graph, _checkpointer

    if _graph is not None:
        return _graph, _checkpointer

    # Initialize LLM
    client = AnthropicProxyClient(
        base_url=os.getenv("OPUS_BASE_URL", "https://opus.abhibots.com"),
        api_key=os.getenv("OPUS_API_KEY"),
        model=os.getenv("OPUS_MODEL", "claude-sonnet-4-20250514")
    )
    llm = AnthropicProxyChatModel(client=client)
    tools = get_tools()
    llm_with_tools = llm.bind_tools(tools)

    # Define nodes
    def agent_node(state: AgentState):
        response = llm_with_tools.invoke(state["messages"])
        return {"messages": [response]}

    # Build graph
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", ToolNode(tools))

    workflow.set_entry_point("agent")

    def should_continue(state: AgentState):
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    workflow.add_conditional_edges("agent", should_continue)
    workflow.add_edge("tools", "agent")

    # Checkpointer for persistence
    _checkpointer = MemorySaver()
    _graph = workflow.compile(checkpointer=_checkpointer)

    return _graph, _checkpointer
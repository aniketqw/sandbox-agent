# agent/graph.py
import os
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import ToolMessage, AIMessage, HumanMessage

from llm.factory import get_chat_model
from tools.langchain_adapter import get_tools
from agent.state import AgentState

MAX_STEPS = 10
MAX_REFLECTIONS = 2   # limit reflection calls per turn

_graph = None
_checkpointer = None

def _count_recent_tool_errors(messages: list, lookback: int = 3) -> tuple[int, int]:
    """
    Returns (error_count, total_tool_messages) from the last `lookback` ToolMessages.
    """
    tool_msgs = [msg for msg in messages if isinstance(msg, ToolMessage)]
    recent = tool_msgs[-lookback:] if len(tool_msgs) >= lookback else tool_msgs
    if not recent:
        return 0, 0
    errors = sum(1 for msg in recent if "error" in msg.content.lower())
    return errors, len(recent)

def get_agent_graph():
    global _graph, _checkpointer
    if _graph is not None:
        return _graph, _checkpointer

    llm = get_chat_model()
    tools = get_tools()
    llm_with_tools = llm.bind_tools(tools)

    # ------------------------------------------------------------
    # Agent Node
    # ------------------------------------------------------------
    def agent_node(state: AgentState):
        messages = state["messages"]
        response = llm_with_tools.invoke(messages)
        return {
            "messages": [response],
            "step_count": state.get("step_count", 0) + 1,
            "reflection_count": state.get("reflection_count", 0)
        }

    # ------------------------------------------------------------
    # Reflection Node
    # ------------------------------------------------------------
    def reflect_node(state: AgentState):
        """
        Analyze recent tool failures and decide next action.
        This node can either:
          - Ask the human for help (by calling ask_human tool automatically)
          - Provide a strategic hint to the agent
        """
        messages = state["messages"]
        error_count, total = _count_recent_tool_errors(messages, lookback=3)

        # Build a reflection prompt based on failure pattern
        if error_count >= 2:
            reflection_msg = (
                "[REFLECTION] I've noticed that the last few tool calls have failed repeatedly. "
                "Possible causes: network issues, malformed arguments, or missing dependencies. "
                "I should consider asking the human for guidance or trying an alternative approach."
            )
            # Automatically ask human if we haven't already in this turn
            if state.get("reflection_count", 0) == 0:
                # Simulate calling ask_human by injecting a tool call
                ask_tool_call = {
                    "id": f"reflect_ask_{state.get('step_count', 0)}",
                    "name": "ask_human",
                    "args": {
                        "question": "I'm encountering repeated tool failures. How should I proceed?"
                    },
                    "type": "tool_call"
                }
                ai_message = AIMessage(content=reflection_msg, tool_calls=[ask_tool_call])
            else:
                ai_message = AIMessage(content=reflection_msg)
        else:
            ai_message = AIMessage(content="[REFLECTION] Some tools failed but I can continue. Adjusting approach.")

        return {
            "messages": [ai_message],
            "step_count": state.get("step_count", 0) + 1,
            "reflection_count": state.get("reflection_count", 0) + 1
        }

    # ------------------------------------------------------------
    # Build Graph
    # ------------------------------------------------------------
    workflow = StateGraph(AgentState)

    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", ToolNode(tools))
    workflow.add_node("reflect", reflect_node)

    workflow.set_entry_point("agent")

    # After agent, decide: tools, reflect, or end
    def after_agent(state: AgentState):
        last_msg = state["messages"][-1]
        if state.get("step_count", 0) >= MAX_STEPS:
            return END
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "tools"
        return END

    workflow.add_conditional_edges("agent", after_agent)

    # After tools, decide: reflect or back to agent
    def after_tools(state: AgentState):
        error_count, total = _count_recent_tool_errors(state["messages"], lookback=3)
        # Trigger reflection if error rate >= 2/3 AND we haven't reflected too many times
        if error_count >= 2 and state.get("reflection_count", 0) < MAX_REFLECTIONS:
            return "reflect"
        return "agent"

    workflow.add_conditional_edges("tools", after_tools)

    # After reflection, go back to agent (or could end if needed)
    workflow.add_edge("reflect", "agent")

    _checkpointer = MemorySaver()
    _graph = workflow.compile(checkpointer=_checkpointer)
    return _graph, _checkpointer
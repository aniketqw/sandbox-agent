# agent/graph.py
import os
import json
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import ToolMessage, AIMessage, HumanMessage, SystemMessage

from llm.factory import get_chat_model
from tools.langchain_adapter import get_tools
from agent.state import AgentState

MAX_STEPS = 15
MAX_REFLECTIONS = 2

_graph = None
_checkpointer = None

def _count_recent_tool_errors(messages: list, lookback: int = 3) -> tuple[int, int]:
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
    # We do NOT bind tools globally; each node will call the LLM with its own prompt and tools as needed.

    # ------------------------------------------------------------
    # Planner Node
    # ------------------------------------------------------------
    def planner_node(state: AgentState):
        # Inject a system message prompting for a concise plan
        plan_prompt = SystemMessage(content=(
            "You are a planning assistant. Based on the user's request, create a concise, "
            "step-by-step plan. Do not execute anything yet. If the plan requires user approval, "
            "call the request_approval tool with the plan summary. Otherwise, just output the plan as text."
        ))
        # Use the LLM with tools bound so it can optionally call request_approval
        llm_with_tools = llm.bind_tools(tools)
        messages = [plan_prompt] + state["messages"]
        response = llm_with_tools.invoke(messages)
        return {
            "messages": [response],
            "step_count": state.get("step_count", 0) + 1,
            "plan": response.content if response.content else None,
            "plan_approved": False
        }

    # ------------------------------------------------------------
    # Approval Node (handles request_approval tool call)
    # ------------------------------------------------------------
    def approval_node(state: AgentState):
        # Check if the planner emitted a request_approval tool call
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            for tc in last_msg.tool_calls:
                if tc["name"] == "request_approval":
                    # Execute the tool (it will prompt user and return result)
                    tool_node = ToolNode(tools)
                    result = tool_node.invoke({"messages": [last_msg]})
                    return {
                        "messages": result["messages"],
                        "step_count": state.get("step_count", 0) + 1,
                        "plan_approved": True  # Assume approval if tool returns success
                    }
        # No approval requested; mark as approved
        return {"plan_approved": True, "step_count": state.get("step_count", 0)}

    # ------------------------------------------------------------
    # Executor Node
    # ------------------------------------------------------------
    def executor_node(state: AgentState):
        # Inject a prompt instructing the LLM to execute the approved plan using tools
        exec_prompt = SystemMessage(content=(
            "You are an execution assistant. Execute the approved plan step by step using the available tools. "
            "If you encounter an error, report it. When finished, output a summary of what was done."
        ))
        llm_with_tools = llm.bind_tools(tools)
        messages = [exec_prompt] + state["messages"]
        response = llm_with_tools.invoke(messages)
        return {
            "messages": [response],
            "step_count": state.get("step_count", 0) + 1
        }

    # ------------------------------------------------------------
    # Reflection Node (check for errors and decide next action)
    # ------------------------------------------------------------
    def reflect_node(state: AgentState):
        error_count, _ = _count_recent_tool_errors(state["messages"], lookback=3)
        if error_count >= 2:
            # Ask human for help
            ask_msg = AIMessage(
                content="I've encountered multiple tool errors. I need your guidance.",
                tool_calls=[{
                    "id": f"reflect_ask_{state.get('step_count', 0)}",
                    "name": "ask_human",
                    "args": {"question": "I'm encountering repeated tool failures. How should I proceed?"},
                    "type": "tool_call"
                }]
            )
            return {
                "messages": [ask_msg],
                "step_count": state.get("step_count", 0) + 1,
                "reflection_count": state.get("reflection_count", 0) + 1
            }
        else:
            # Continue execution
            return {"step_count": state.get("step_count", 0)}

    # ------------------------------------------------------------
    # Build Graph
    # ------------------------------------------------------------
    workflow = StateGraph(AgentState)

    workflow.add_node("planner", planner_node)
    workflow.add_node("approval", approval_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("tools", ToolNode(tools))
    workflow.add_node("reflect", reflect_node)

    workflow.set_entry_point("planner")

    # After planner: if tool_calls present, go to approval (to handle request_approval), else go directly to executor
    def after_planner(state: AgentState):
        if state.get("step_count", 0) >= MAX_STEPS:
            return END
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            # Check if it's request_approval
            if any(tc["name"] == "request_approval" for tc in last_msg.tool_calls):
                return "approval"
        # Otherwise, go to executor (plan was just text, no approval needed)
        return "executor"

    workflow.add_conditional_edges("planner", after_planner)

    # After approval, go to executor
    workflow.add_edge("approval", "executor")

    # After executor: if tool_calls -> tools, else check for errors -> reflect or end
    def after_executor(state: AgentState):
        if state.get("step_count", 0) >= MAX_STEPS:
            return END
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "tools"
        # No more tool calls; check if we should reflect
        error_count, _ = _count_recent_tool_errors(state["messages"], lookback=3)
        if error_count >= 2 and state.get("reflection_count", 0) < MAX_REFLECTIONS:
            return "reflect"
        return END

    workflow.add_conditional_edges("executor", after_executor, {"tools": "tools", "reflect": "reflect", END: END})

    # After tools: back to executor to continue
    workflow.add_edge("tools", "executor")

    # After reflection: if there's a tool call (ask_human), go to tools; otherwise back to executor
    def after_reflect(state: AgentState):
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "tools"
        return "executor"

    workflow.add_conditional_edges("reflect", after_reflect, {"tools": "tools", "executor": "executor"})

    _checkpointer = MemorySaver()
    _graph = workflow.compile(checkpointer=_checkpointer)
    return _graph, _checkpointer
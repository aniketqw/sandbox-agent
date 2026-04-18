# agent/graph.py
import os
import json
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command
from langchain_core.messages import ToolMessage, AIMessage, HumanMessage, SystemMessage

from llm.factory import get_chat_model
from tools.langchain_adapter import get_tools
from agent.state import AgentState

MAX_STEPS = 20
MAX_REFLECTIONS = 3

_graph = None
_checkpointer = None

def _count_recent_tool_errors(messages: list, lookback: int = 3) -> tuple[int, list]:
    tool_msgs = [msg for msg in messages if isinstance(msg, ToolMessage)]
    recent = tool_msgs[-lookback:] if len(tool_msgs) >= lookback else tool_msgs
    errors = [msg.content for msg in recent if "error" in msg.content.lower()]
    return len(errors), errors

def get_agent_graph():
    global _graph, _checkpointer
    if _graph is not None:
        return _graph, _checkpointer

    llm = get_chat_model()
    tools = get_tools()
    tool_node = ToolNode(tools)

    # ------------------------------------------------------------
    # Plan Node
    # ------------------------------------------------------------
    def plan_node(state: AgentState):
        llm_with_tools = llm.bind_tools(tools)
        plan_prompt = SystemMessage(content=(
            "You are a planning assistant. Create a concise step-by-step plan to address the user's request. "
            "If you need to fetch data or research, you may use tools (e.g., http_request, web_search) immediately. "
            "After gathering necessary information, summarize the plan for approval."
        ))
        messages = [plan_prompt] + state["messages"]
        response = llm_with_tools.invoke(messages)
        return {
            "messages": [response],
            "plan": response.content if response.content else None,
            "step_count": state.get("step_count", 0) + 1,
        }

    # ------------------------------------------------------------
    # Approval Node
    # ------------------------------------------------------------
    def approval_node(state: AgentState):
        plan_summary = state.get("plan", "No plan was generated.")
        user_decision = interrupt({
            "type": "approval_request",
            "plan": plan_summary,
            "message": "Please review the plan. Approve, edit, or reject."
        })
        if user_decision.get("type") == "approve":
            return {"plan_approved": True}  # No step_count
        elif user_decision.get("type") == "edit":
            feedback = user_decision.get("feedback", "Please revise the plan.")
            return {
                "messages": [HumanMessage(content=f"User feedback: {feedback}")],
                "plan_approved": False,
            }
        else:
            return {
                "messages": [AIMessage(content="Plan was rejected by the user.")],
                "plan_approved": False,
            }

    # ------------------------------------------------------------
    # Execute Node
    # ------------------------------------------------------------
    def execute_node(state: AgentState):
        llm_with_tools = llm.bind_tools(tools)
        exec_prompt = SystemMessage(content=(
            "You are an execution assistant. Execute the approved plan step-by-step using the available tools. "
            "If you encounter an error, report it. When finished, output a summary of what was done."
        ))
        messages = [exec_prompt] + state["messages"]
        response = llm_with_tools.invoke(messages)
        return {
            "messages": [response],
            "step_count": state.get("step_count", 0) + 1,
            "reflection_count": 0,
        }

    # ------------------------------------------------------------
    # Reflect Node
    # ------------------------------------------------------------
    def reflect_node(state: AgentState):
        error_count, errors = _count_recent_tool_errors(state["messages"], lookback=3)
        if error_count == 0:
            return {"step_count": state.get("step_count", 0)}
        error_details = "\n".join(errors)
        reflection_prompt = HumanMessage(content=(
            f"The following tool call errors occurred:\n{error_details}\n"
            "Analyze these errors and suggest a corrected tool call or a different approach. "
            "Provide a new tool call to try, or ask the human for help if you are unsure."
        ))
        llm_with_tools = llm.bind_tools(tools)
        messages = state["messages"] + [reflection_prompt]
        response = llm_with_tools.invoke(messages)
        return {
            "messages": [response],
            "step_count": state.get("step_count", 0) + 1,
            "reflection_count": state.get("reflection_count", 0) + 1,
        }

    # ------------------------------------------------------------
    # Ask Human Node
    # ------------------------------------------------------------
    def ask_human_node(state: AgentState):
        ask_msg = AIMessage(
            content="I'm having trouble completing this task after several attempts. I need your guidance.",
            tool_calls=[{
                "id": f"ask_human_{state.get('step_count', 0)}",
                "name": "ask_human",
                "args": {"question": "I'm encountering repeated tool failures. What should I do differently?"},
                "type": "tool_call"
            }]
        )
        return {
            "messages": [ask_msg],
            "step_count": state.get("step_count", 0) + 1,
        }

    # ------------------------------------------------------------
    # Graph Construction
    # ------------------------------------------------------------
    workflow = StateGraph(AgentState)

    workflow.add_node("plan", plan_node)
    workflow.add_node("approval", approval_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("tools", tool_node)
    workflow.add_node("reflect", reflect_node)
    workflow.add_node("ask_human", ask_human_node)

    workflow.set_entry_point("plan")

    # After plan: if tool_calls -> tools, else -> approval
    def after_plan(state: AgentState):
        if state.get("step_count", 0) >= MAX_STEPS:
            return END
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "tools"
        else:
            return "approval"

    workflow.add_conditional_edges("plan", after_plan)

    # After tools called from plan: go back to plan to incorporate results
    workflow.add_edge("tools", "plan")

    # Approval routing
    def after_approval(state: AgentState):
        if state.get("plan_approved"):
            return "execute"
        else:
            return "plan"

    workflow.add_conditional_edges("approval", after_approval)

    # Execute routing
    def after_execute(state: AgentState):
        if state.get("step_count", 0) >= MAX_STEPS:
            return END
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "tools"
        else:
            error_count, _ = _count_recent_tool_errors(state["messages"], lookback=3)
            if error_count > 0 and state.get("reflection_count", 0) < MAX_REFLECTIONS:
                return "reflect"
            return END

    workflow.add_conditional_edges("execute", after_execute, {"tools": "tools", "reflect": "reflect", END: END})
    workflow.add_edge("tools", "execute")

    # Reflect routing
    def after_reflect(state: AgentState):
        if state.get("step_count", 0) >= MAX_STEPS:
            return END
        if state.get("reflection_count", 0) >= MAX_REFLECTIONS:
            return "ask_human"
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "tools"
        else:
            return "execute"

    workflow.add_conditional_edges("reflect", after_reflect, {"tools": "tools", "execute": "execute", "ask_human": "ask_human"})

    workflow.add_edge("ask_human", "execute")

    _checkpointer = MemorySaver()
    _graph = workflow.compile(checkpointer=_checkpointer)
    return _graph, _checkpointer
# agent/graph.py
import os
import json
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command
from langchain_core.messages import ToolMessage, AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool

from llm.factory import get_chat_model
from tools.langchain_adapter import get_tools
from agent.state import AgentState

MAX_STEPS = 30
MAX_REFLECTIONS = 2

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
    all_tools = get_tools()
    tool_node = ToolNode(all_tools)

    # ------------------------------------------------------------
    # Handoff Tools for Supervisor → Worker delegation
    # ------------------------------------------------------------
    def make_handoff_tool(worker_name: str):
        """Creates a tool that the supervisor uses to delegate a task to a worker."""
        @tool(worker_name)
        def handoff(task_description: str):
            """Call this to assign a sub-task to the worker."""
            return {"assigned_to": worker_name, "task": task_description}
        return handoff

    supervisor_tools = [
        make_handoff_tool("coder"),
        make_handoff_tool("researcher"),
    ]

    # ------------------------------------------------------------
    # Supervisor Node (The Master)
    # ------------------------------------------------------------
    supervisor_llm = llm.bind_tools(supervisor_tools)

    def supervisor_node(state: AgentState):
        # First, think step by step to formulate a plan
        think_prompt = SystemMessage(content=(
            "You are the supervisor agent. Your job is to analyze the user's request and create a high-level plan. "
            "If the task requires writing or executing code, delegate it to the 'coder' worker. "
            "If it requires web research, delegate it to the 'researcher' worker. "
            "You may also use tools directly if needed. After gathering results, synthesize a final answer."
        ))
        messages = [think_prompt] + state["messages"]
        response = supervisor_llm.invoke(messages)
        return {
            "messages": [response],
            "plan": response.content if response.content else None,
        }

    # ------------------------------------------------------------
    # Coder Worker (Specialized Agent)
    # ------------------------------------------------------------
    # Filter tools for the coder
    coder_tools = [t for t in all_tools if t.name in ["execute_python", "write_file", "read_file", "run_shell_command"]]
    coder_agent = create_react_agent(
        llm, coder_tools,
        prompt="You are a coding specialist. Write and execute Python code to solve assigned tasks. Report results clearly."
    )

    def coder_node(state: AgentState):
        # Extract the last handoff task for the coder
        last_msg = state["messages"][-1]
        task_description = ""
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            for tc in last_msg.tool_calls:
                if tc["name"] == "coder":
                    task_description = tc["args"].get("task_description", "")
                    break
        if not task_description:
            return {"messages": [AIMessage(content="No task provided for coder.")]}

        # Create a sub-state for the worker
        worker_messages = [HumanMessage(content=f"Complete this task: {task_description}")]
        result = coder_agent.invoke({"messages": worker_messages})
        return {
            "messages": result["messages"],
            "worker_results": [{"worker": "coder", "task": task_description, "output": result["messages"][-1].content}],
        }

    # ------------------------------------------------------------
    # Researcher Worker (Web Search Specialist)
    # ------------------------------------------------------------
    researcher_tools = [t for t in all_tools if t.name in ["web_search", "http_request"]]
    researcher_agent = create_react_agent(
        llm, researcher_tools,
        prompt="You are a research specialist. Use web_search and http_request to gather information."
    )

    def researcher_node(state: AgentState):
        last_msg = state["messages"][-1]
        task_description = ""
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            for tc in last_msg.tool_calls:
                if tc["name"] == "researcher":
                    task_description = tc["args"].get("task_description", "")
                    break
        if not task_description:
            return {"messages": [AIMessage(content="No task provided for researcher.")]}

        worker_messages = [HumanMessage(content=f"Complete this task: {task_description}")]
        result = researcher_agent.invoke({"messages": worker_messages})
        return {
            "messages": result["messages"],
            "worker_results": [{"worker": "researcher", "task": task_description, "output": result["messages"][-1].content}],
        }

    # ------------------------------------------------------------
    # Human Approval Node (Interrupts for feedback)
    # ------------------------------------------------------------
    def approval_node(state: AgentState):
        plan_summary = state.get("plan", "No plan was generated.")
        user_decision = interrupt({
            "type": "approval_request",
            "plan": plan_summary,
            "message": "Please review the plan. Approve, edit, or reject."
        })
        if user_decision.get("type") == "approve":
            return {"plan_approved": True}
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
    # Build Graph
    # ------------------------------------------------------------
    workflow = StateGraph(AgentState)

    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("coder", coder_node)
    workflow.add_node("researcher", researcher_node)
    workflow.add_node("tools", tool_node)
    workflow.add_node("approval", approval_node)

    workflow.set_entry_point("supervisor")

    # After supervisor: if handoff tool called -> go to that worker; else -> approval
    def after_supervisor(state: AgentState):
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            for tc in last_msg.tool_calls:
                if tc["name"] in ["coder", "researcher"]:
                    return tc["name"]
            # If other tool calls, go to tools
            return "tools"
        # No tool calls, check if we need approval
        if not state.get("plan_approved", False):
            return "approval"
        return END

    workflow.add_conditional_edges("supervisor", after_supervisor, {"coder": "coder", "researcher": "researcher", "tools": "tools", "approval": "approval", END: END})

    # Workers return to supervisor after completion
    workflow.add_edge("coder", "supervisor")
    workflow.add_edge("researcher", "supervisor")
    workflow.add_edge("tools", "supervisor")

    # Approval goes back to supervisor to re-plan or proceed
    workflow.add_edge("approval", "supervisor")

    _checkpointer = MemorySaver()
    _graph = workflow.compile(checkpointer=_checkpointer)
    return _graph, _checkpointer
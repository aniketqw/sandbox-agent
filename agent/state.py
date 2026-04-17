# agent/state.py
from typing import TypedDict, Annotated, Optional
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    step_count: int
    reflection_count: int
    plan: Optional[str]           # stores the generated plan summary
    plan_approved: bool            # whether user approved the plan
# agent/state.py
from typing import TypedDict, Annotated, Optional, List
from langgraph.graph.message import add_messages

def merge_step_count(left: int, right: int) -> int:
    """Reducer for step_count: take the maximum value."""
    return max(left, right)

def merge_reflection_count(left: int, right: int) -> int:
    """Reducer for reflection_count: take the maximum value."""
    return max(left, right)

def merge_plan_approved(left: bool, right: bool) -> bool:
    """Reducer for plan_approved: True if either is True."""
    return left or right

def merge_plan(left: Optional[str], right: Optional[str]) -> Optional[str]:
    """Reducer for plan: keep the latest non-None value."""
    return right if right is not None else left

def merge_tool_errors(left: List[str], right: List[str]) -> List[str]:
    """Reducer for tool_errors: combine lists, keep last 10."""
    combined = left + right
    return combined[-10:]  # Keep only recent errors

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    step_count: Annotated[int, merge_step_count]
    reflection_count: Annotated[int, merge_reflection_count]
    plan: Annotated[Optional[str], merge_plan]
    plan_approved: Annotated[bool, merge_plan_approved]
    tool_errors: Annotated[List[str], merge_tool_errors]
# agent/state.py
from typing import TypedDict, Annotated, Optional, List, Dict, Any
from langgraph.graph.message import add_messages
import operator

def merge_max(left: int, right: int) -> int:
    """Reducer that takes the maximum of two values."""
    return max(left, right)

def merge_or(left: bool, right: bool) -> bool:
    """Reducer that returns True if either is True."""
    return left or right

def merge_errors(left: List[str], right: List[str]) -> List[str]:
    """Reducer that concatenates and keeps last 10 errors."""
    combined = left + right
    return combined[-10:]

def merge_plan(left: Optional[str], right: Optional[str]) -> Optional[str]:
    """Reducer that keeps the latest non-None plan."""
    return right if right is not None else left

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    plan: Annotated[Optional[str], merge_plan]
    plan_approved: Annotated[bool, merge_or]
    worker_tasks: Annotated[List[Dict[str, Any]], operator.add]
    worker_results: Annotated[List[Dict[str, Any]], operator.add]
    tool_errors: Annotated[List[str], merge_errors]
    step_count: Annotated[int, merge_max]
    reflection_count: Annotated[int, merge_max]
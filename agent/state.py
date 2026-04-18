from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

def merge_max(left: int, right: int) -> int:
    return max(left, right)

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    step_count: Annotated[int, merge_max]
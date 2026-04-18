# agent/workers.py
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from tools.implementations import execute_python, write_file

# Create a focused toolset for the coder
@tool
def run_python(code: str):
    """Executes the provided python code in the sandbox."""
    return execute_python(code)

coder_tools = [run_python, write_file]

def create_coder_agent(llm):
    """Creates a ReAct agent specialized in writing and executing code."""
    return create_react_agent(
        llm, coder_tools,
        prompt="You are a coding specialist. Write and execute python code to solve tasks."
    )
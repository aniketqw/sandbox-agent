"""
harness.py — LangGraph-powered agent with checkpointing and LangSmith.
"""

import os
import sys
from dotenv import load_dotenv
from langsmith import traceable
from langchain_core.messages import HumanMessage, SystemMessage
import logging
from sandbox.container import start_sandbox
from agent import get_agent_graph

load_dotenv()
MAX_STEPS = 10
# Enable LangSmith if API key present
if os.getenv("LANGSMITH_API_KEY"):
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGSMITH_PROJECT", "sandbox-agent")

# Set logging to WARNING to keep terminal clean
logging.basicConfig(level=logging.WARNING)

SYSTEM_PROMPT = """You are a powerful coding assistant with access to an isolated Docker sandbox that has full internet access.
You can execute shell commands, Python code, and automate a web browser (using Playwright) safely.

Your available tools:
- run_shell_command: Run any shell command (install packages, manage files, etc.)
  Arguments: { "command": "<shell command string>" }
- execute_python: Write and run Python code
  Arguments: { "code": "<complete Python script as a string>" }
- write_file: Save text files to /workspace
  Arguments: { "filename": "<name>", "content": "<text>" }
- read_file: Read files from /workspace
  Arguments: { "filename": "<name>" }
- http_request: Perform HTTP GET/POST requests. Large response bodies are saved to file and a summary is returned.
  Arguments: { "url": "<url>", "method": "GET"|"POST", "data": "<optional body>", "headers": <optional dict> }
- grep_file: Search for regex patterns inside a file, returning matching lines with line numbers.
  Arguments: { "filepath": "<path>", "pattern": "<regex>", "max_lines": <int> }
- read_file_range: Read a specific range of lines from a file.
  Arguments: { "filepath": "<path>", "start_line": <int>, "end_line": <int> }
- list_files: List files and directories inside a given path.
  Arguments: { "directory": "<path>" }
- install_python_package: Install pip packages inside the sandbox.
  Arguments: { "packages": ["pkg1", "pkg2", ...] }
- run_playwright_script: Execute a Playwright script (Playwright + Chromium are pre-installed).
  Arguments: { "script": "<Python code using Playwright>" }
- ask_human: Ask the human user a question when you are stuck, need clarification, or want to confirm an action.
  Arguments: { "question": "<your question to the user>" }

Guidelines:
1. **Use the exact tool names and argument formats shown above.** Provide all required arguments with the correct types.
2. For execute_python, provide the complete Python code as a single string in the `code` argument. Do not pass other fields.
3. For http_request, provide the `url` and optionally `method`. The default method is GET.
4. When http_request returns a 'full_response_file' field, the response body was too large to include directly.
   Use grep_file to search for specific information, or read_file_range to inspect portions of the file.
5. **IMPORTANT**: When a tool returns data, **always quote the exact output** in your final response.
   Do not invent, summarize, or alter the tool's output unless the user explicitly asks for a summary.
6. The sandbox has full internet access. Standard library and pip-installable packages are available.
7. This is an educational environment. Do not violate any website's Terms of Service.
8. Report results clearly, including stdout/stderr/exit codes from the sandbox.
9. **You have persistent memory across conversation turns.** You can refer to previous interactions and files.
10. **If a tool fails repeatedly or you are uncertain how to proceed, use ask_human to get help.**
    After receiving feedback, continue with the task using the new information.
11. After several unsuccessful attempts, pause and reflect on what might be wrong, then adjust your approach or ask for help.
"""

@traceable
def run_agent(state: dict, thread_id: str):
    graph, _ = get_agent_graph()
    config = {"configurable": {"thread_id": thread_id}}
    final_state = graph.invoke(state, config=config)
    return final_state

def main():
    provider = os.getenv("LLM_PROVIDER", "opus").upper()
    if provider == "OPUS":
        model = os.getenv("OPUS_MODEL", "claude-sonnet-4-20250514")
    else:
        model = os.getenv("OLLAMA_MODEL", "llama3.2")

    print("=" * 60)
    print("  🤖  LangGraph Sandbox Agent")
    print(f"  LLM: {provider} / {model}")
    print("  Sandbox: Docker")
    print("=" * 60)

    start_sandbox()
    get_agent_graph()  # Initialize

    print("\nSandbox agent ready. Type your request (or 'exit' to quit).\n")

    thread_id = "main-user-session"
    # Initial state includes messages and step counter
    state = {
        "messages": [SystemMessage(content=SYSTEM_PROMPT)],
        "step_count": 0
    }

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[Agent] Interrupted. Shutting down...")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye"):
            print("[Agent] Goodbye!")
            break

        # Append user message to state
        state["messages"].append(HumanMessage(content=user_input))
        # Reset step count for new user turn
        state["step_count"] = 0

        graph, _ = get_agent_graph()
        config = {"configurable": {"thread_id": thread_id}}

        print("\n[Agent] Thinking...")
        # Stream events for real-time feedback
        for event in graph.stream(state, config=config):
            for node_name, node_output in event.items():
                if node_name == "agent":
                    msg = node_output.get("messages", [])[-1]
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        print(f"[Agent] Calling tools: {[tc['name'] for tc in msg.tool_calls]}")
                elif node_name == "tools":
                    print("[Agent] Tools executed.")

        # Get final state after the turn
        final_state = graph.get_state(config)
        if final_state and final_state.values:
            state = final_state.values
            last_msg = state["messages"][-1]
            if state.get("step_count", 0) >= MAX_STEPS:
                print("\n[Agent] Reached maximum steps. Final response:")
            print(f"\n{'='*60}")
            print(f"Agent: {last_msg.content}")
            print(f"{'='*60}")
        else:
            print("[Agent] No response received.")

if __name__ == "__main__":
    main()
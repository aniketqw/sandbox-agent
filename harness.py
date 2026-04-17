"""
harness.py — LangGraph-powered agent with checkpointing and LangSmith.
"""

import os
import sys
from dotenv import load_dotenv
from langsmith import traceable
from langchain_core.messages import HumanMessage, SystemMessage

from sandbox import start_sandbox
from agent_graph import get_agent_graph

# Load environment variables
load_dotenv()

# Enable LangSmith if API key present
if os.getenv("LANGSMITH_API_KEY"):
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGSMITH_PROJECT", "sandbox-agent")

SYSTEM_PROMPT = """You are a powerful coding assistant with access to an isolated Docker sandbox that has full internet access.
You can execute shell commands, Python code, and automate a web browser (using Playwright) safely.

Your available tools:
- run_shell_command: Run any shell command (install packages, manage files, etc.)
- execute_python: Write and run Python code
- write_file: Save text files to /workspace
- read_file: Read files from /workspace
- http_request: Perform HTTP GET/POST requests. Large response bodies are saved to file and a summary is returned.
- grep_file: Search for regex patterns inside a file, returning matching lines with line numbers.
- read_file_range: Read a specific range of lines from a file.
- list_files: List files and directories inside a given path.
- install_python_package: Install pip packages inside the sandbox.
- run_playwright_script: Execute a Playwright script (Playwright + Chromium are pre-installed).

Guidelines:
1. ALWAYS verify your approach by actually running code — don't just describe what you'd do.
2. For web automation tasks, use run_playwright_script with a complete, well-written Python script.
3. If a Python package is missing, use install_python_package before executing scripts that require it.
4. When http_request returns a 'full_response_file' field, the response body was too large to include directly.
   DO NOT attempt to read the entire file with read_file. Instead, use grep_file to search for specific information,
   or read_file_range to inspect portions of the file. Use list_files to locate saved response files if needed.
5. **IMPORTANT**: When a tool returns data, **always quote the exact output** in your final response.
   Do not invent, summarize, or alter the tool's output unless the user explicitly asks for a summary.
6. The sandbox has full internet access. Standard library and pip-installable packages are available.
7. This is an educational environment. Do not attempt to violate any website's Terms of Service.
   If asked to automate LinkedIn, explain the ethical concerns and proceed only with a mock/demo site.
8. Report results clearly, including the actual stdout/stderr/exit codes from the sandbox.
"""

@traceable
def run_agent(messages: list, thread_id: str):
    graph, _ = get_agent_graph()
    config = {"configurable": {"thread_id": thread_id}}
    final_state = graph.invoke({"messages": messages}, config=config)
    return final_state["messages"]

def main():
    print("=" * 60)
    print("  🤖  LangGraph Sandbox Agent")
    print("  Model: Opus Proxy /", os.getenv("OPUS_MODEL", "claude-sonnet-4-20250514"))
    print("  Sandbox: Docker")
    print("=" * 60)

    # Start sandbox
    start_sandbox()

    # Get agent graph (initializes LLM and tools)
    get_agent_graph()

    print("\nSandbox agent ready. Type your request (or 'exit' to quit).\n")

    # Session ID for memory
    thread_id = "main-user-session"

    # Initial system message
    messages = [SystemMessage(content=SYSTEM_PROMPT)]

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

        messages.append(HumanMessage(content=user_input))

        # Run agent with streaming output
        graph, _ = get_agent_graph()
        config = {"configurable": {"thread_id": thread_id}}

        print("\n[Agent] Thinking...")
        # Stream events for real-time feedback
        for event in graph.stream({"messages": messages}, config=config):
            for node_name, node_output in event.items():
                if node_name == "agent":
                    msg = node_output.get("messages", [])[-1]
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        print(f"[Agent] Calling tools: {[tc['name'] for tc in msg.tool_calls]}")
                elif node_name == "tools":
                    print("[Agent] Tools executed.")

        # Retrieve final state to get the last message
        final_state = graph.get_state(config)
        if final_state and final_state.values:
            final_messages = final_state.values.get("messages", [])
            if final_messages:
                last_msg = final_messages[-1]
                print(f"\n{'='*60}")
                print(f"Agent: {last_msg.content}")
                print(f"{'='*60}")
                # Update messages with full conversation for next turn
                messages = final_messages
        else:
            print("[Agent] No response received.")

if __name__ == "__main__":
    main()
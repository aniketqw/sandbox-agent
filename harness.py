"""
harness.py — LangGraph-powered agent with checkpointing and LangSmith.
Clean terminal UI using Rich. Supports Plan → Approval → Execute → Reflect flow.
"""

import os
import sys
from dotenv import load_dotenv
from langsmith import traceable
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from langgraph.types import Command
import logging

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich import print as rprint

from sandbox.container import start_sandbox
from agent import get_agent_graph

load_dotenv()

# Enable LangSmith if API key present
if os.getenv("LANGSMITH_API_KEY"):
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGSMITH_PROJECT", "sandbox-agent")

# Suppress noisy logs
logging.basicConfig(level=logging.WARNING)

console = Console()

SYSTEM_PROMPT = """You are a powerful coding assistant with access to an isolated Docker sandbox that has full internet access.
You can execute shell commands, Python code, automate a web browser, and search the web.

Your available tools:
- run_shell_command: Run any shell command.
  Arguments: { "command": "<shell command string>" }
- execute_python: Run Python code.
  Arguments: { "code": "<complete Python script as a string>" }
- write_file: Save text files to /workspace.
  Arguments: { "filename": "<name>", "content": "<text>" }
- read_file: Read files from /workspace.
  Arguments: { "filename": "<name>" }
- http_request: Perform HTTP requests. Large responses are saved to file.
  Arguments: { "url": "<url>", "method": "GET"|"POST", "data": "<optional body>", "headers": <optional dict> }
- grep_file: Search for regex patterns inside a file.
  Arguments: { "filepath": "<path>", "pattern": "<regex>", "max_lines": <int> }
- read_file_range: Read a specific range of lines from a file.
  Arguments: { "filepath": "<path>", "start_line": <int>, "end_line": <int> }
- list_files: List files and directories.
  Arguments: { "directory": "<path>" }
- install_python_package: Install pip packages.
  Arguments: { "packages": ["pkg1", "pkg2", ...] }
- run_playwright_script: Execute a Playwright script (Chromium pre-installed).
  Arguments: { "script": "<Python code using Playwright>" }
- web_search: Search the web using Tavily to get up-to-date information or research a topic.
  Arguments: { "query": "<search query>", "max_results": <int> }
- ask_human: Ask the human user a question when you are stuck or need clarification.
  Arguments: { "question": "<your question to the user>" }
- request_approval: Request user approval before executing a plan.
  Arguments: { "plan_summary": "<summary of your plan>", "code_to_execute": "<optional code>" }

Guidelines:
1. **Think step by step and create a clear plan before acting.**
2. If you need information not in your training data or want to research a topic, use web_search.
3. For multi-step tasks, summarize your plan and use request_approval to get user confirmation before executing.
4. After approval, execute the plan using the available tools.
5. When the task is complete, save the final results or a summary to a file in /workspace (e.g., result.txt, report.json).
6. **Use the exact tool names and argument formats shown above.** Provide all required arguments with the correct types.
7. For execute_python, provide the complete Python code as a single string in the `code` argument.
8. For http_request, provide the `url` and optionally `method`. Default is GET.
9. When http_request returns a 'full_response_file' field, use grep_file or read_file_range to explore it.
10. **IMPORTANT**: When a tool returns data, **always quote the exact output** in your final response.
11. The sandbox has full internet access. Standard library and pip-installable packages are available.
12. This is an educational environment. Do not violate any website's Terms of Service.
13. Report results clearly, including stdout/stderr/exit codes from the sandbox.
14. **You have persistent memory across conversation turns.** You can refer to previous interactions and files.
15. **If a tool fails repeatedly or you are uncertain how to proceed, use ask_human to get help.**
16. After several unsuccessful attempts, pause and reflect on what might be wrong, then adjust your approach or ask for help.
"""


def _extract_tool_results(messages: list) -> str:
    """Extract the most recent tool results for a fallback summary."""
    results = []
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            content = msg.content
            if len(content) > 500:
                content = content[:500] + "..."
            results.append(f"- {msg.name}: {content}")
        if len(results) >= 3:
            break
    return "\n".join(results) if results else "No tool results available."


def main():
    provider = os.getenv("LLM_PROVIDER", "opus").upper()
    if provider == "OPUS":
        model = os.getenv("OPUS_MODEL", "claude-sonnet-4-20250514")
    else:
        model = os.getenv("OLLAMA_MODEL", "llama3.2")

    console.print(Panel.fit(
        f"[bold cyan]🤖 LangGraph Sandbox Agent[/]\n"
        f"LLM: {provider} / {model}\n"
        f"Sandbox: Docker",
        title="Welcome",
        border_style="cyan"
    ))

    start_sandbox()
    get_agent_graph()

    console.print("[green]✓ Sandbox ready.[/]\n")

    thread_id = "main-user-session"
    state = {
        "messages": [SystemMessage(content=SYSTEM_PROMPT)],
        "step_count": 0,
        "reflection_count": 0,
        "plan": None,
        "plan_approved": False,
        "tool_errors": []
    }

    while True:
        try:
            user_input = console.input("[bold yellow]You:[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Interrupted. Shutting down...[/]")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye"):
            console.print("[green]Goodbye![/]")
            break

        # Reset per-turn state
        state["messages"].append(HumanMessage(content=user_input))
        state["step_count"] = 0
        state["reflection_count"] = 0
        state["plan"] = None
        state["plan_approved"] = False
        state["tool_errors"] = []

        graph, _ = get_agent_graph()
        config = {"configurable": {"thread_id": thread_id}}

        console.print("[cyan]Agent is planning...[/]")

        try:
            # Stream to handle interrupts (approval requests)
            for event in graph.stream(state, config=config):
                if 'interrupt' in event:
                    interrupt_data = event['interrupt']
                    console.print()
                    console.print(Panel(
                        f"[bold yellow]📋 Approval Required[/]\n\n"
                        f"[bold]Plan:[/]\n{interrupt_data['plan']}\n\n"
                        f"{interrupt_data['message']}",
                        title="Awaiting Human Input",
                        border_style="yellow"
                    ))
                    # Get user decision
                    decision = console.input("[bold green]Approve / Edit / Reject? (a/e/r): [/]").strip().lower()
                    if decision == 'a':
                        user_feedback = {"type": "approve"}
                    elif decision == 'e':
                        feedback = console.input("[bold]Please provide feedback to edit the plan: [/]")
                        user_feedback = {"type": "edit", "feedback": feedback}
                    else:  # 'r' or anything else
                        user_feedback = {"type": "reject"}

                    # Resume graph with the user's decision
                    final_state = graph.invoke(Command(resume=user_feedback), config=config)
                    state = final_state
                    break  # Exit the event loop after handling interrupt
                else:
                    # Normal event (no interrupt) – update state with the latest
                    for node_name, node_output in event.items():
                        if node_output and "messages" in node_output:
                            state = node_output
            else:
                # If we didn't break (no interrupt), the stream finished normally
                # The last event is the final state
                pass

        except Exception as e:
            console.print(f"[red]Error during execution: {e}[/]")
            import traceback
            traceback.print_exc()
            continue

        # Display final response
        last_msg = state["messages"][-1] if state.get("messages") else None
        if isinstance(last_msg, AIMessage) and last_msg.content:
            console.print()
            console.print(Panel(
                Markdown(last_msg.content),
                title="Agent Response",
                border_style="green"
            ))
        else:
            # Fallback: show summary of tool results
            summary = _extract_tool_results(state.get("messages", []))
            console.print()
            console.print(Panel(
                f"[yellow]The agent completed its tasks but did not produce a final message.[/]\n\n"
                f"**Last tool results:**\n{summary}",
                title="Agent Summary",
                border_style="yellow"
            ))

        # Optionally show step count if limit reached
        if state.get("step_count", 0) >= 20:
            console.print("[dim]Reached maximum steps for this turn.[/]")

if __name__ == "__main__":
    main()
"""
harness.py — LangGraph-powered agent with checkpointing and LangSmith.
Clean terminal UI using Rich.
"""

import os
import sys
from dotenv import load_dotenv
from langsmith import traceable
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
import logging

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.spinner import Spinner
from rich.live import Live
from rich.table import Table
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
        "reflection_count": 0
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

        state["messages"].append(HumanMessage(content=user_input))
        state["step_count"] = 0
        state["reflection_count"] = 0

        graph, _ = get_agent_graph()
        config = {"configurable": {"thread_id": thread_id}}

        # Use a live display to show progress
        with Live(console=console, refresh_per_second=4, transient=True) as live:
            live.update(Spinner("dots", text="[cyan]Thinking...[/]"))
            try:
                final_state = graph.invoke(state, config=config)
            except Exception as e:
                console.print(f"[red]Error during execution: {e}[/]")
                continue

        state = final_state
        last_msg = state["messages"][-1]

        # Display final response
        if isinstance(last_msg, AIMessage) and last_msg.content:
            console.print()
            console.print(Panel(
                Markdown(last_msg.content),
                title="Agent Response",
                border_style="green"
            ))
        else:
            # Fallback: show summary of tool results
            summary = _extract_tool_results(state["messages"])
            console.print()
            console.print(Panel(
                f"[yellow]The agent completed its tasks but did not produce a final message.[/]\n\n"
                f"**Last tool results:**\n{summary}",
                title="Agent Summary",
                border_style="yellow"
            ))

        # Optionally show step count if limit reached
        if state.get("step_count", 0) >= 10:
            console.print("[dim]Reached maximum steps for this turn.[/]")

if __name__ == "__main__":
    main()
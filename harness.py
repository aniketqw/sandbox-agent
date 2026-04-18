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

CRITICAL RULES:

1. For execute_python, the argument MUST be named `code` and contain the full Python script as a string. Do NOT pass `filename` or any other argument.
2. When given a multi‑step task, you MUST complete ALL steps. Do NOT stop after the first tool call.
3. After a tool returns, immediately continue with the next logical step.
4. If you need to extract data from a JSON response, use execute_python to parse it and print the result.
5. Only provide a final summary after ALL steps are completed.
6. When http_request returns a 'full_response_file' field, use execute_python to read and parse the JSON file.
7. If you are uncertain or stuck, use ask_human.


Guidelines:
- **Use the exact tool names and argument formats shown above.**
- For execute_python, provide the complete Python code as a single string in the `code` argument.
- For http_request, provide the `url` and optionally `method`. Default is GET.
- Report results clearly, including stdout/stderr/exit codes from the sandbox.
- You have persistent memory across conversation turns. Refer to previous interactions and files.
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
        model = os.getenv("OLLAMA_MODEL", "qwen2.5")

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

        # Append user message and reset step counter for this turn
        state["messages"].append(HumanMessage(content=user_input))
        state["step_count"] = 0

        graph, _ = get_agent_graph()
        config = {"configurable": {"thread_id": thread_id}}

        console.print("[cyan]Thinking...[/]")
        try:
            final_state = graph.invoke(state, config=config)
        except Exception as e:
            console.print(f"[red]Error during execution: {e}[/]")
            continue

        state = final_state
        last_msg = state["messages"][-1]

        if isinstance(last_msg, AIMessage) and last_msg.content:
            console.print()
            console.print(Panel(
                Markdown(last_msg.content),
                title="Agent",
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

if __name__ == "__main__":
    main()
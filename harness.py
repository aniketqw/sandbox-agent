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

SYSTEM_PROMPT = """... (same as before) ..."""

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
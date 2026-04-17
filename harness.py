"""
harness.py — The main entry point.
Implements the ReAct (Reason + Act) loop connecting Ollama → Docker sandbox.

Run with:
    python harness.py
"""

import json
import sys
from openai import OpenAI

from sandbox import start_sandbox
from tools import TOOL_DISPATCH
from schemas import TOOLS

# ── Configuration ──────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_API_KEY  = "ollama"          # Ollama doesn't need a real key
MODEL           = "qwen2.5"          # Change to "mistral" or another pulled model
MAX_ITERATIONS  = 10                # Safety limit: max tool calls per user turn

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

def format_tool_result(tool_name: str, result: dict) -> str:
    """Format a tool result as a readable string for the LLM."""
    lines = [f"Tool: {tool_name}", f"Result: {json.dumps(result, indent=2)}"]
    return "\n".join(lines)


def run_agent_turn(client: OpenAI, messages: list) -> list:
    """
    Execute one full ReAct cycle for a user message.
    Loops until the LLM returns a natural-language response (no more tool calls).

    Returns the updated messages list.
    """
    iteration = 0

    while iteration < MAX_ITERATIONS:
        iteration += 1
        print(f"\n[Agent] Calling LLM (iteration {iteration})...")

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",    # Let the model decide when to use tools
        )

        message = response.choices[0].message

        # ── Case 1: Model wants to call tools ─────────────────────────────────
        if message.tool_calls:
            # Append the assistant's tool_calls message to history
            messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id":       tc.id,
                        "type":     "function",
                        "function": {
                            "name":      tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ],
            })

            # Execute each tool call and append results
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError as e:
                    args = {}
                    print(f"[Agent] Warning: Could not parse tool args: {e}")

                print(f"[Agent] Executing tool: {tool_name}({list(args.keys())})")

                if tool_name in TOOL_DISPATCH:
                    result = TOOL_DISPATCH[tool_name](**args)
                else:
                    result = {"error": f"Unknown tool: {tool_name}"}

                # Append the tool result to message history
                messages.append({
                    "role":         "tool",
                    "tool_call_id": tool_call.id,
                    "name":         tool_name,
                    "content":      json.dumps(result),
                })

        # ── Case 2: Model is done — natural language response ─────────────────
        else:
            final_response = message.content or "(No response)"
            messages.append({
                "role":    "assistant",
                "content": final_response,
            })
            print(f"\n{'='*60}")
            print(f"Agent: {final_response}")
            print(f"{'='*60}")
            return messages  # Done with this turn

    # If we hit the iteration limit
    print(f"\n[Agent] Reached max iterations ({MAX_ITERATIONS}). Stopping.")
    messages.append({
        "role":    "assistant",
        "content": f"I've reached the maximum number of steps ({MAX_ITERATIONS}). Please refine your request.",
    })
    return messages


def main():
    print("=" * 60)
    print("  🤖  Local Sandbox Agent")
    print("  Model: Ollama /", MODEL)
    print("  Sandbox: Docker (python:3.11-slim)")
    print("=" * 60)

    # Phase 1: Start the Docker sandbox
    start_sandbox()

    # Phase 2: Initialize the OpenAI client pointed at Ollama
    client = OpenAI(
        base_url=OLLAMA_BASE_URL,
        api_key=OLLAMA_API_KEY,
    )

    # Phase 3: Initialize conversation with system prompt
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    print("\nSandbox agent ready. Type your request (or 'exit' to quit).\n")

    # Phase 4: Main REPL loop
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

        # Append user message and run the ReAct loop
        messages.append({"role": "user", "content": user_input})
        messages = run_agent_turn(client, messages)

    # atexit in sandbox.py handles container cleanup automatically


if __name__ == "__main__":
    main()

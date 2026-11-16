"""
mcp_server/server.py — Exposes the sandbox as an MCP server so Claude Code,
ChatGPT/Codex, or any other MCP-speaking host can execute code in *your*
persistent Docker container instead of their own opaque hosted sandbox.

Every tool call here goes through core.executor.execute_tool(), so it gets
the same policy gate and audit/LangSmith trace as the local LangGraph agent
(agent/graph.py) — same execution core, same observability, different caller.

Transports:
  stdio            — default; what Claude Code's `claude mcp add` expects.
  streamable-http  — for ChatGPT developer-mode connectors, the OpenAI Agents
                     SDK, and Codex CLI, which don't support local stdio.

Usage:
  python -m mcp_server.server                       # stdio (Claude Code)
  python -m mcp_server.server --http --port 8765     # streamable HTTP

The caller identity recorded in every audit/trace entry comes from the
SANDBOX_MCP_CALLER env var (set it per host in your MCP config — see
mcp_server/claude_code.mcp.json.example and mcp_server/codex.config.toml.example)
and defaults to "mcp-client" if unset.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import sys

from mcp.server.mcpserver import MCPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.executor import execute_tool, UnknownToolError  # noqa: E402

CALLER = os.getenv("SANDBOX_MCP_CALLER", "mcp-client")
DEFAULT_TIMEOUT_S = 120

mcp = MCPServer(
    name="sandbox-exec",
    instructions=(
        "Execute shell/Python/browser automation in a persistent, user-owned "
        "Docker container instead of your own hosted sandbox. Every call is "
        "policy-gated (some commands are denied or require approval) and "
        "logged to an audit trail + LangSmith trace you can inspect with "
        "get_audit_log / get_trace_url. Prefer these tools over any local "
        "shell/bash tool you already have for this workspace."
    ),
)

_executor_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="sandbox-mcp")


def _run_with_timeout(tool_name: str, args: dict, timeout_seconds: int) -> dict:
    future = _executor_pool.submit(execute_tool, tool_name, args, caller=CALLER)
    try:
        return future.result(timeout=timeout_seconds)
    except concurrent.futures.TimeoutError:
        return {
            "error": f"Tool '{tool_name}' timed out after {timeout_seconds}s.",
            "timed_out": True,
            "note": "The underlying container process may still be running; "
                    "it was not killed client-side.",
        }
    except UnknownToolError as e:
        return {"error": str(e)}


@mcp.tool()
def run_shell(command: str, timeout_seconds: int = DEFAULT_TIMEOUT_S) -> dict:
    """Run a shell command inside the sandbox container's /workspace."""
    return _run_with_timeout("run_shell_command", {"command": command}, timeout_seconds)


@mcp.tool()
def run_python(code: str, timeout_seconds: int = DEFAULT_TIMEOUT_S) -> dict:
    """Run a complete Python script inside the sandbox container's /workspace."""
    return _run_with_timeout("execute_python", {"code": code}, timeout_seconds)


@mcp.tool()
def write_file(filename: str, content: str) -> dict:
    """Write a text file to the sandbox's /workspace."""
    return _run_with_timeout("write_file", {"filename": filename, "content": content}, DEFAULT_TIMEOUT_S)


@mcp.tool()
def read_file(filename: str) -> dict:
    """Read a text file from the sandbox's /workspace."""
    return _run_with_timeout("read_file", {"filename": filename}, DEFAULT_TIMEOUT_S)


@mcp.tool()
def list_files(directory: str = "/workspace") -> dict:
    """List files and directories inside the sandbox."""
    return _run_with_timeout("list_files", {"directory": directory}, DEFAULT_TIMEOUT_S)


@mcp.tool()
def install_package(packages: list[str], timeout_seconds: int = 300) -> dict:
    """Install one or more pip packages inside the sandbox. Requires policy approval."""
    return _run_with_timeout("install_python_package", {"packages": packages}, timeout_seconds)


@mcp.tool()
def run_playwright(script: str, timeout_seconds: int = 300) -> dict:
    """Run a Playwright browser-automation script inside the sandbox. Requires policy approval."""
    return _run_with_timeout("run_playwright_script", {"script": script}, timeout_seconds)


@mcp.tool()
def get_audit_log(limit: int = 50) -> dict:
    """Return the most recent audit-log entries for this session — what ran,
    its exit code/duration, and any policy decision — so you can answer
    'what have you run so far and why' about your own actions."""
    from core.audit import read_audit_log, get_session_id
    return {"session_id": get_session_id(), "entries": read_audit_log(limit=limit)}


@mcp.tool()
def get_trace_url() -> dict:
    """Return the LangSmith project URL for this session's traces, if LangSmith
    tracing is configured, so the human can inspect the full run tree."""
    from core.audit import get_trace_url_info
    return get_trace_url_info()


def main() -> None:
    parser = argparse.ArgumentParser(description="sandbox-agent MCP server")
    parser.add_argument("--http", action="store_true", help="Serve over streamable HTTP instead of stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.http:
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

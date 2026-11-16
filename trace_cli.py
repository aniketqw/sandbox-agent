#!/usr/bin/env python3
"""
trace_cli.py — Tail the sandbox's audit log live while Claude Code, ChatGPT,
or the local agent works, and print the LangSmith run-tree URL for the
session.

Usage:
    python trace_cli.py                       # follow the most recent session
    python trace_cli.py --session <id>         # follow a specific session
    python trace_cli.py --list                 # list known sessions
    python trace_cli.py --no-follow            # print existing entries and exit
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from core.audit import AUDIT_DIR, get_trace_url_info  # noqa: E402

try:
    from rich.console import Console
    from rich.table import Table
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


def _list_sessions() -> list[str]:
    if not os.path.isdir(AUDIT_DIR):
        return []
    files = sorted(
        (f for f in os.listdir(AUDIT_DIR) if f.endswith(".jsonl")),
        key=lambda f: os.path.getmtime(os.path.join(AUDIT_DIR, f)),
    )
    return [f[: -len(".jsonl")] for f in files]


def _latest_session() -> str | None:
    sessions = _list_sessions()
    return sessions[-1] if sessions else None


def _format_entry(entry: dict) -> str:
    tool = entry.get("tool", "?")
    caller = entry.get("caller", "?")
    policy = entry.get("policy") or {}
    action = policy.get("action", "allow")
    executed = entry.get("executed", True)
    duration = entry.get("duration_s", 0)
    exit_code = entry.get("exit_code")
    ts = entry.get("ts", "")

    if action == "deny":
        status = "DENIED"
    elif action == "approve" and not executed:
        status = "NEEDS APPROVAL"
    elif entry.get("error"):
        status = f"ERROR"
    else:
        status = f"exit={exit_code}" if exit_code is not None else "ok"

    return f"[{ts}] {caller:<12} {tool:<24} {status:<16} {duration:>6.3f}s"


def _print_entries(entries: list[dict]) -> None:
    if not entries:
        return
    if HAS_RICH:
        console = Console()
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Time")
        table.add_column("Caller")
        table.add_column("Tool")
        table.add_column("Status")
        table.add_column("Duration", justify="right")
        for e in entries:
            policy = e.get("policy") or {}
            action = policy.get("action", "allow")
            if action == "deny":
                status = "[red]DENIED[/]"
            elif action == "approve" and not e.get("executed", True):
                status = "[yellow]NEEDS APPROVAL[/]"
            elif e.get("error"):
                status = "[red]ERROR[/]"
            else:
                exit_code = e.get("exit_code")
                status = f"exit={exit_code}" if exit_code is not None else "ok"
            table.add_row(
                e.get("ts", ""),
                e.get("caller", "?"),
                e.get("tool", "?"),
                status,
                f"{e.get('duration_s', 0):.3f}s",
            )
        console.print(table)
    else:
        for e in entries:
            print(_format_entry(e))


def main() -> None:
    parser = argparse.ArgumentParser(description="Tail the sandbox-agent audit log")
    parser.add_argument("--session", help="Session id to follow (default: most recent)")
    parser.add_argument("--list", action="store_true", help="List known session ids and exit")
    parser.add_argument("--no-follow", action="store_true", help="Print existing entries and exit (don't tail)")
    args = parser.parse_args()

    if args.list:
        sessions = _list_sessions()
        if not sessions:
            print("No sessions logged yet.")
        for s in sessions:
            print(s)
        return

    session_id = args.session or _latest_session()
    if session_id is None:
        print(f"No audit sessions found under {AUDIT_DIR}. Run the agent or MCP server first.")
        return

    path = os.path.join(AUDIT_DIR, f"{session_id}.jsonl")
    print(f"Session: {session_id}")
    trace_info = get_trace_url_info()
    if trace_info.get("tracing_enabled"):
        print(f"LangSmith: {trace_info['url']}  ({trace_info['note']})")
    else:
        print(f"LangSmith: disabled ({trace_info.get('note', '')})")
    print(f"Audit log: {path}\n")

    seen = 0

    def _flush_new():
        nonlocal seen
        if not os.path.exists(path):
            return
        with open(path, "r") as f:
            lines = f.readlines()
        new_lines = lines[seen:]
        seen = len(lines)
        entries = [json.loads(l) for l in new_lines if l.strip()]
        _print_entries(entries)

    _flush_new()
    if args.no_follow:
        return

    print("Following... (Ctrl+C to stop)\n")
    try:
        while True:
            time.sleep(1)
            _flush_new()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()

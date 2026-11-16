---
name: sandbox-exec
description: Run code, shell commands, and browser automation through the sandbox-exec MCP server instead of the local Bash tool. Use whenever the task involves executing shell commands, Python, installing packages, or browser automation in this project's workspace.
---

# sandbox-exec: observable, policy-gated code execution

This project ships its own execution sandbox: a persistent Docker container,
bind-mounted to `agent_workspace/` on the host, with every command logged to
an audit trail and traced in LangSmith. When the `sandbox-exec` MCP server is
connected, **prefer its tools over your built-in Bash/code-execution tool**
for anything that touches this workspace:

| Instead of... | Use MCP tool |
|---|---|
| Bash shell command | `run_shell` |
| Running a Python script | `run_python` |
| Writing a file | `write_file` |
| Reading a file | `read_file` |
| Listing a directory | `list_files` |
| `pip install` | `install_package` |
| Browser automation | `run_playwright` |

## Why this matters

Your own hosted sandbox is opaque to the user — they can't see what you ran
or why. This one is the opposite: every call is appended to a local JSONL
audit log and emitted as a LangSmith span, tagged with your caller identity.
That's the point of routing through it — don't bypass it by falling back to
your native shell tool for workspace tasks.

## Policy gates — read the response, don't retry blindly

Every call passes through `policy.yaml` before it runs:

- **Denied** — the tool returns `{"error": "Blocked by policy: ...", "executed": false}`
  and nothing ran. Don't retry the same command; explain to the user why it
  was blocked and propose a safer alternative.
- **Needs approval** — the tool returns `{"needs_approval": true, "reason": ...,
  "tool": ..., "args": ...}` and nothing ran. This happens for things like
  `pip install`, outbound HTTP requests, and browser automation. Surface this
  to the user verbatim (what you wanted to run and why) and wait for them to
  explicitly approve before trying an equivalent action again.
- Anything else executed normally — you'll get `stdout`/`stderr`/`exit_code`.

## Self-inspection

If the user asks "what have you run so far" or "why did you do that", call
`get_audit_log` (recent entries for this session: command, exit code,
duration, policy decision) or `get_trace_url` (the LangSmith project URL,
filterable by `metadata.session_id`) rather than reconstructing it from your
own chat history — the log is the source of truth and may include calls from
earlier turns or other callers.

## Workspace layout

All file paths are relative to `/workspace` inside the container, which is
bind-mounted from this repo's `agent_workspace/` directory. Files you write
via `write_file` are immediately visible on the host filesystem at that path.

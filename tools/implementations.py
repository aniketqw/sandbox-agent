"""
tools/implementations.py — Functions the agent can call to interact with the sandbox.
"""

import os
import json
from datetime import datetime
from sandbox.container import get_container, WORKSPACE_CONTAINER
from tavily import TavilyClient
import requests  # Add this import at the top
TEMP_SCRIPT = os.path.join(WORKSPACE_CONTAINER, "agent_temp.py")
HTTP_RESPONSE_DIR = os.path.join(WORKSPACE_CONTAINER, "http_responses")

# ------------------------------------------------------------
# Core Tools
# ------------------------------------------------------------

# In tools/implementations.py
def http_request(url: str, method: str = "GET", data: str = None, headers: dict = None) -> dict:
    if method is None:
        method = "GET"
    container = get_container()
    print(f"\n[Tool] http_request: {method} {url}")

    container.exec_run(cmd=["sh", "-c", f"mkdir -p {HTTP_RESPONSE_DIR}"])
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    response_file = os.path.join(HTTP_RESPONSE_DIR, f"resp_{timestamp}.json")

    # Combined script: try requests first, fallback to curl
    # Saves ONLY the response body to the file, prints metadata as JSON
    script = f"""
import json
import subprocess
import sys

url = {json.dumps(url)}
method = {json.dumps(method)}
data = {repr(data)}
headers = {repr(headers) if headers else 'None'}

def fetch_with_requests():
    import requests
    if method == 'GET':
        resp = requests.get(url, headers=headers, verify=False, timeout=30)
    else:
        resp = requests.post(url, headers=headers, data=data, verify=False, timeout=30)
    # Try to parse JSON, fallback to text
    try:
        body = resp.json()
    except:
        body = resp.text
    # Save ONLY the body to file
    with open("{response_file}", "w") as f:
        if isinstance(body, (dict, list)):
            json.dump(body, f)
        else:
            f.write(str(body))
    return {{"status": resp.status_code, "body": body}}

def fetch_with_curl():
    curl_cmd = ["curl", "-s", "-k", "-X", method, url]
    if method == "POST" and data is not None:
        curl_cmd.extend(["-d", str(data)])
    result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=30)
    body = result.stdout
    try:
        body = json.loads(body)
    except:
        pass
    # Save ONLY the body to file
    with open("{response_file}", "w") as f:
        if isinstance(body, (dict, list)):
            json.dump(body, f)
        else:
            f.write(str(body))
    return {{"status": 200 if result.returncode == 0 else 500, "body": body}}

try:
    output = fetch_with_requests()
except Exception as e:
    try:
        output = fetch_with_curl()
    except Exception as e2:
        output = {{"error": f"Both requests and curl failed: {{e}} | {{e2}}"}}

print(json.dumps(output))
"""
    safe_script = script.replace("'", "'\\''")
    write_cmd = f"printf '%s' '{safe_script}' > /tmp/http_req.py"
    container.exec_run(cmd=["sh", "-c", write_cmd])
    result = container.exec_run(cmd=["python", "/tmp/http_req.py"], demux=True)

    stdout = result.output[0].decode("utf-8", errors="replace") if result.output[0] else ""
    stderr = result.output[1].decode("utf-8", errors="replace") if result.output[1] else ""

    try:
        parsed = json.loads(stdout) if stdout else {"error": "No output", "stderr": stderr}
    except json.JSONDecodeError:
        parsed = {"error": "Failed to parse JSON", "raw_stdout": stdout, "stderr": stderr}

    # If the response body is large, return a preview instead of the full body
    body = parsed.get("body")
    if body is not None:
        body_str = json.dumps(body) if isinstance(body, (dict, list)) else str(body)
        if len(body_str) > 2000:
            body_preview = body_str[:500] + "... [truncated]"
            return {
                "status": parsed.get("status"),
                "body_preview": body_preview,
                "full_response_file": response_file,
                "note": f"Full response saved to {response_file}"
            }
    return parsed




def web_search(query: str, max_results: int = 5) -> dict:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return {"error": "TAVILY_API_KEY not set in environment."}
    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(query, max_results=max_results)
        results = []
        for r in response.get("results", []):
            results.append({
                "title": r.get("title"),
                "url": r.get("url"),
                "content": r.get("content"),
                "score": r.get("score")
            })
        return {"query": query, "results": results, "count": len(results)}
    except Exception as e:
        return {"error": str(e)}


def ask_human(question: str) -> dict:
    from rich.console import Console
    from rich.panel import Panel
    console = Console()
    console.print(Panel(f"[bold yellow]🤔 {question}[/]", title="Agent needs your input", border_style="yellow"))
    response = console.input("[bold green]Your answer: [/]")
    return {"answer": response}


def request_approval(plan_summary: str, code_to_execute: str = "") -> dict:
    from rich.console import Console
    from rich.panel import Panel
    from rich.syntax import Syntax
    console = Console()
    console.print()
    console.print(Panel(
        f"[bold yellow]📋 Agent wants to execute:[/]\n\n{plan_summary}",
        title="Approval Request",
        border_style="yellow"
    ))
    if code_to_execute:
        console.print(Panel(
            Syntax(code_to_execute, "python", theme="monokai", line_numbers=True),
            title="Code to execute",
            border_style="yellow"
        ))
    answer = console.input("[bold green]Approve? (y/n): [/]").strip().lower()
    if answer in ("y", "yes"):
        feedback = console.input("[bold]Optional feedback: [/]") or "Approved."
        return {"approved": True, "feedback": feedback}
    else:
        feedback = console.input("[bold]What should be changed? [/]") or "Not approved."
        return {"approved": False, "feedback": feedback}


# ------------------------------------------------------------
# Other Tools (unchanged)
# ------------------------------------------------------------

def run_shell_command(command: str) -> dict:
    container = get_container()
    print(f"\n[Tool] run_shell_command: {command}")
    result = container.exec_run(cmd=["sh", "-c", command], workdir=WORKSPACE_CONTAINER, demux=True)
    stdout = result.output[0].decode("utf-8", errors="replace") if result.output[0] else ""
    stderr = result.output[1].decode("utf-8", errors="replace") if result.output[1] else ""
    exit_code = result.exit_code
    print(f"[Tool] Exit code: {exit_code}")
    return {"stdout": stdout, "stderr": stderr, "exit_code": exit_code}


def execute_python(code: str) -> dict:
    container = get_container()
    print(f"\n[Tool] execute_python:\n{code}\n")
    escaped = code.replace("'", "'\\''")
    write_cmd = f"cat > {TEMP_SCRIPT} << 'PYEOF'\n{code}\nPYEOF"
    container.exec_run(cmd=["sh", "-c", write_cmd])
    result = container.exec_run(cmd=["python", TEMP_SCRIPT], workdir=WORKSPACE_CONTAINER, demux=True)
    stdout = result.output[0].decode("utf-8", errors="replace") if result.output[0] else ""
    stderr = result.output[1].decode("utf-8", errors="replace") if result.output[1] else ""
    exit_code = result.exit_code
    print(f"[Tool] Exit code: {exit_code}")
    return {"stdout": stdout, "stderr": stderr, "exit_code": exit_code}


def write_file(filename: str, content: str) -> dict:
    container = get_container()
    filepath = os.path.join(WORKSPACE_CONTAINER, filename)
    print(f"\n[Tool] write_file: {filepath}")
    safe_content = content.replace("'", "'\\''")
    write_cmd = f"printf '%s' '{safe_content}' > {filepath}"
    result = container.exec_run(cmd=["sh", "-c", write_cmd])
    success = result.exit_code == 0
    return {"success": success, "path": filepath, "message": f"File written to {filepath}" if success else "Write failed"}


def read_file(filename: str) -> dict:
    container = get_container()
    filepath = os.path.join(WORKSPACE_CONTAINER, filename)
    print(f"\n[Tool] read_file: {filepath}")
    result = container.exec_run(cmd=["cat", filepath], demux=True)
    if result.exit_code != 0:
        stderr = result.output[1].decode("utf-8", errors="replace") if result.output[1] else "Unknown error"
        return {"error": stderr}
    content = result.output[0].decode("utf-8", errors="replace") if result.output[0] else ""
    return {"content": content}


def install_python_package(packages: list) -> dict:
    container = get_container()
    pkgs = " ".join(packages)
    print(f"\n[Tool] install_python_package: {pkgs}")
    cmd = f"pip install --quiet {pkgs}"
    result = container.exec_run(cmd=["sh", "-c", cmd], demux=True)
    stdout = result.output[0].decode("utf-8", errors="replace") if result.output[0] else ""
    stderr = result.output[1].decode("utf-8", errors="replace") if result.output[1] else ""
    success = result.exit_code == 0
    verify_cmd = f"python -c 'import {packages[0]}' 2>/dev/null && echo 'OK' || echo 'FAIL'"
    verify_result = container.exec_run(cmd=["sh", "-c", verify_cmd])
    verified = verify_result.output.decode().strip() == "OK"
    return {"success": success, "verified": verified, "stdout": stdout, "stderr": stderr, "packages": packages}


def run_playwright_script(script: str) -> dict:
    container = get_container()
    print(f"\n[Tool] run_playwright_script (length={len(script)})")
    temp_script = "/tmp/playwright_script.py"
    write_cmd = f"cat > {temp_script} << 'PYEOF'\n{script}\nPYEOF"
    container.exec_run(cmd=["sh", "-c", write_cmd])
    result = container.exec_run(cmd=["python", temp_script], workdir=WORKSPACE_CONTAINER, demux=True)
    stdout = result.output[0].decode("utf-8", errors="replace") if result.output[0] else ""
    stderr = result.output[1].decode("utf-8", errors="replace") if result.output[1] else ""
    exit_code = result.exit_code
    print(f"[Tool] Playwright exit code: {exit_code}")
    return {"stdout": stdout, "stderr": stderr, "exit_code": exit_code}


def grep_file(filepath: str, pattern: str, max_lines: int = 50) -> dict:
    container = get_container()
    print(f"\n[Tool] grep_file: '{pattern}' in {filepath}")
    cmd = f"grep -n -E '{pattern}' {filepath} | head -n {max_lines}"
    result = container.exec_run(cmd=["sh", "-c", cmd], demux=True)
    stdout = result.output[0].decode("utf-8", errors="replace") if result.output[0] else ""
    stderr = result.output[1].decode("utf-8", errors="replace") if result.output[1] else ""
    if result.exit_code == 1 and not stdout:
        return {"matches": [], "message": "No matches found."}
    elif result.exit_code != 0:
        return {"error": stderr or "grep command failed"}
    matches = stdout.strip().split("\n") if stdout.strip() else []
    return {"matches": matches, "count": len(matches)}


def read_file_range(filepath: str, start_line: int = 1, end_line: int = 100) -> dict:
    container = get_container()
    print(f"\n[Tool] read_file_range: {filepath} lines {start_line}-{end_line}")
    cmd = f"sed -n '{start_line},{end_line}p' {filepath}"
    result = container.exec_run(cmd=["sh", "-c", cmd], demux=True)
    stdout = result.output[0].decode("utf-8", errors="replace") if result.output[0] else ""
    stderr = result.output[1].decode("utf-8", errors="replace") if result.output[1] else ""
    if result.exit_code != 0:
        return {"error": stderr or "Failed to read file"}
    return {"content": stdout, "start_line": start_line, "end_line": end_line}


def list_files(directory: str = WORKSPACE_CONTAINER) -> dict:
    container = get_container()
    print(f"\n[Tool] list_files: {directory}")
    cmd = f"ls -la {directory}"
    result = container.exec_run(cmd=["sh", "-c", cmd], demux=True)
    stdout = result.output[0].decode("utf-8", errors="replace") if result.output[0] else ""
    stderr = result.output[1].decode("utf-8", errors="replace") if result.output[1] else ""
    return {"stdout": stdout, "stderr": stderr, "exit_code": result.exit_code}


# Dispatch table
TOOL_DISPATCH = {
    "run_shell_command": run_shell_command,
    "execute_python": execute_python,
    "write_file": write_file,
    "read_file": read_file,
    "http_request": http_request,
    "install_python_package": install_python_package,
    "run_playwright_script": run_playwright_script,
    "grep_file": grep_file,
    "read_file_range": read_file_range,
    "list_files": list_files,
    "ask_human": ask_human,
    "web_search": web_search,
    "request_approval": request_approval,
}
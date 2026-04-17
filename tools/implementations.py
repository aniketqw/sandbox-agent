"""
tools.py — Functions the agent can call to interact with the sandbox.
Each function maps 1-to-1 with a JSON schema defined in schemas.py.
"""

import os
import json
from datetime import datetime
from sandbox.container import get_container, WORKSPACE_CONTAINER

TEMP_SCRIPT = os.path.join(WORKSPACE_CONTAINER, "agent_temp.py")
HTTP_RESPONSE_DIR = os.path.join(WORKSPACE_CONTAINER, "http_responses")

def ask_human(question: str) -> dict:
    """Ask the human user a question and wait for a response."""
    print(f"\n[Agent needs your input] {question}")
    response = input("Your answer: ").strip()
    return {"answer": response}

def http_request(url: str, method: str = "GET", data: str = None, headers: dict = None) -> dict:
    container = get_container()
    print(f"\n[Tool] http_request: {method} {url}")

    container.exec_run(cmd=["sh", "-c", f"mkdir -p {HTTP_RESPONSE_DIR}"])

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    response_file = os.path.join(HTTP_RESPONSE_DIR, f"resp_{timestamp}.json")

    data_repr = repr(data)
    headers_repr = repr(headers)

    script = f"""
import urllib.request
import json

url = {json.dumps(url)}
method = {json.dumps(method)}
data = {data_repr}
headers = {headers_repr}

req = urllib.request.Request(url, method=method)
if headers is not None:
    for k, v in headers.items():
        req.add_header(k, v)
if data is not None and method == "POST":
    req.data = data.encode('utf-8')

try:
    with urllib.request.urlopen(req) as response:
        status = response.status
        resp_headers = dict(response.headers)
        body = response.read().decode('utf-8', errors='replace')
        output = {{"status": status, "headers": resp_headers, "body": body}}
        with open("{response_file}", "w") as f:
            json.dump(output, f)
        print(json.dumps(output))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
    safe_script = script.replace("'", "'\\''")
    write_cmd = f"printf '%s' '{safe_script}' > /tmp/http_req.py"
    container.exec_run(cmd=["sh", "-c", write_cmd])

    result = container.exec_run(cmd=["python", "/tmp/http_req.py"], demux=True)

    stdout = result.output[0].decode("utf-8", errors="replace") if result.output[0] else ""
    stderr = result.output[1].decode("utf-8", errors="replace") if result.output[1] else ""

    print(f"[Tool] HTTP stdout preview: {stdout[:200]}...")
    if stderr:
        print(f"[Tool] HTTP stderr: {stderr[:200]}...")

    try:
        parsed = json.loads(stdout) if stdout else {"error": "No output", "stderr": stderr}
    except json.JSONDecodeError:
        parsed = {"error": "Failed to parse JSON", "raw_stdout": stdout, "stderr": stderr}

    if "body" in parsed and len(parsed.get("body", "")) > 2000:
        body_preview = parsed["body"][:500] + "... [truncated]"
        return {
            "status": parsed.get("status"),
            "headers": parsed.get("headers"),
            "body_preview": body_preview,
            "full_response_file": response_file,
            "note": f"Response body too large ({len(parsed['body'])} chars). Full response saved to {response_file}. Use grep_file or read_file_range to explore it."
        }
    return parsed

def install_python_package(packages: list) -> dict:
    """
    Install one or more pip packages inside the sandbox.
    """
    container = get_container()
    pkgs = " ".join(packages)
    print(f"\n[Tool] install_python_package: {pkgs}")

    cmd = f"pip install --quiet {pkgs}"
    result = container.exec_run(cmd=["sh", "-c", cmd], demux=True)

    stdout = result.output[0].decode("utf-8", errors="replace") if result.output[0] else ""
    stderr = result.output[1].decode("utf-8", errors="replace") if result.output[1] else ""
    success = result.exit_code == 0

    # Quick verification
    verify_cmd = f"python -c 'import {packages[0]}' 2>/dev/null && echo 'OK' || echo 'FAIL'"
    verify_result = container.exec_run(cmd=["sh", "-c", verify_cmd])
    verified = verify_result.output.decode().strip() == "OK"

    return {
        "success": success,
        "verified": verified,
        "stdout": stdout,
        "stderr": stderr,
        "packages": packages,
    }


def run_playwright_script(script: str) -> dict:
    """
    Run a Playwright automation script inside the sandbox.
    Assumes Playwright and Chromium are pre-installed.
    """
    container = get_container()
    print(f"\n[Tool] run_playwright_script (length={len(script)})")

    temp_script = "/tmp/playwright_script.py"
    write_cmd = f"cat > {temp_script} << 'PYEOF'\n{script}\nPYEOF"
    container.exec_run(cmd=["sh", "-c", write_cmd])

    result = container.exec_run(
        cmd=["python", temp_script],
        workdir=WORKSPACE_CONTAINER,
        demux=True,
    )

    stdout = result.output[0].decode("utf-8", errors="replace") if result.output[0] else ""
    stderr = result.output[1].decode("utf-8", errors="replace") if result.output[1] else ""
    exit_code = result.exit_code

    print(f"[Tool] Playwright exit code: {exit_code}")
    if stdout:
        print(f"[Tool] Playwright stdout:\n{stdout}")
    if stderr:
        print(f"[Tool] Playwright stderr:\n{stderr}")

    return {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
    }


def run_shell_command(command: str) -> dict:
    """
    Execute a shell command inside the sandbox container.
    """
    container = get_container()
    print(f"\n[Tool] run_shell_command: {command}")

    result = container.exec_run(
        cmd=["sh", "-c", command],
        workdir=WORKSPACE_CONTAINER,
        demux=True,
    )

    stdout = result.output[0].decode("utf-8", errors="replace") if result.output[0] else ""
    stderr = result.output[1].decode("utf-8", errors="replace") if result.output[1] else ""
    exit_code = result.exit_code

    print(f"[Tool] Exit code: {exit_code}")
    if stdout:
        print(f"[Tool] stdout:\n{stdout}")
    if stderr:
        print(f"[Tool] stderr:\n{stderr}")

    return {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
    }


def execute_python(code: str) -> dict:
    """
    Write Python code to a temp file inside the sandbox and execute it.
    """
    container = get_container()
    print(f"\n[Tool] execute_python:\n{code}\n")

    # Escape single quotes for the heredoc
    escaped = code.replace("'", "'\\''")
    write_cmd = f"cat > {TEMP_SCRIPT} << 'PYEOF'\n{code}\nPYEOF"
    container.exec_run(cmd=["sh", "-c", write_cmd])

    result = container.exec_run(
        cmd=["python", TEMP_SCRIPT],
        workdir=WORKSPACE_CONTAINER,
        demux=True,
    )

    stdout = result.output[0].decode("utf-8", errors="replace") if result.output[0] else ""
    stderr = result.output[1].decode("utf-8", errors="replace") if result.output[1] else ""
    exit_code = result.exit_code

    print(f"[Tool] Exit code: {exit_code}")
    if stdout:
        print(f"[Tool] stdout:\n{stdout}")
    if stderr:
        print(f"[Tool] stderr:\n{stderr}")

    return {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
    }


def write_file(filename: str, content: str) -> dict:
    """
    Write a file to the /workspace directory inside the sandbox.
    """
    container = get_container()
    filepath = os.path.join(WORKSPACE_CONTAINER, filename)
    print(f"\n[Tool] write_file: {filepath}")

    # Use printf to safely handle special characters
    safe_content = content.replace("'", "'\\''")
    write_cmd = f"printf '%s' '{safe_content}' > {filepath}"
    result = container.exec_run(cmd=["sh", "-c", write_cmd])

    success = result.exit_code == 0
    return {
        "success": success,
        "path": filepath,
        "message": f"File written to {filepath}" if success else "Write failed",
    }


def read_file(filename: str) -> dict:
    """
    Read a file from the /workspace directory inside the sandbox.
    """
    container = get_container()
    filepath = os.path.join(WORKSPACE_CONTAINER, filename)
    print(f"\n[Tool] read_file: {filepath}")

    result = container.exec_run(
        cmd=["cat", filepath],
        demux=True,
    )

    if result.exit_code != 0:
        stderr = result.output[1].decode("utf-8", errors="replace") if result.output[1] else "Unknown error"
        return {"error": stderr}

    content = result.output[0].decode("utf-8", errors="replace") if result.output[0] else ""
    return {"content": content}


def grep_file(filepath: str, pattern: str, max_lines: int = 50) -> dict:
    """
    Search for lines matching a regex pattern in a file.
    Returns matching lines with line numbers.
    """
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
    """
    Read a specific range of lines from a file.
    """
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
    """
    List files and directories in a given path inside the sandbox.
    """
    container = get_container()
    print(f"\n[Tool] list_files: {directory}")

    cmd = f"ls -la {directory}"
    result = container.exec_run(cmd=["sh", "-c", cmd], demux=True)

    stdout = result.output[0].decode("utf-8", errors="replace") if result.output[0] else ""
    stderr = result.output[1].decode("utf-8", errors="replace") if result.output[1] else ""

    return {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": result.exit_code
    }


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
}
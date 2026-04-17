"""
tools.py — Functions the agent can call to interact with the sandbox.
Each function maps 1-to-1 with a JSON schema defined in schemas.py.
"""

import os
import json
from sandbox import get_container, WORKSPACE_CONTAINER

TEMP_SCRIPT = os.path.join(WORKSPACE_CONTAINER, "agent_temp.py")


def http_request(url: str, method: str = "GET", data: str = None, headers: dict = None) -> dict:
    """
    Perform an HTTP request inside the sandbox using urllib (built-in).
    Returns a clear dict with status, headers, and body.
    """
    container = get_container()
    print(f"\n[Tool] http_request: {method} {url}")

    # Build a self-contained Python script that uses urllib
    script = f"""
import urllib.request
import urllib.parse
import json

url = {json.dumps(url)}
method = {json.dumps(method)}
data = {json.dumps(data)}
headers = {json.dumps(headers) if headers else 'None'}

req = urllib.request.Request(url, method=method)
if headers:
    for k, v in headers.items():
        req.add_header(k, v)
if data and method == "POST":
    req.data = data.encode('utf-8')

try:
    with urllib.request.urlopen(req) as response:
        status = response.status
        resp_headers = dict(response.headers)
        body = response.read().decode('utf-8', errors='replace')
        print(json.dumps({{"status": status, "headers": resp_headers, "body": body}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
    temp_file = "/tmp/http_req.py"
    container.exec_run(cmd=["sh", "-c", f"cat > {temp_file} << 'EOF'\n{script}\nEOF"])

    result = container.exec_run(cmd=["python", temp_file], demux=True)

    stdout = result.output[0].decode("utf-8", errors="replace") if result.output[0] else ""
    stderr = result.output[1].decode("utf-8", errors="replace") if result.output[1] else ""

    print(f"[Tool] HTTP stdout: {stdout[:200]}...")  # preview

    try:
        parsed = json.loads(stdout) if stdout else {"error": "No output"}
    except json.JSONDecodeError:
        parsed = {"error": "Failed to parse JSON", "raw_stdout": stdout, "stderr": stderr}

    # For better LLM consumption, if body is huge, truncate it
    if "body" in parsed and len(parsed.get("body", "")) > 2000:
        parsed["body"] = parsed["body"][:2000] + "... [truncated]"
        parsed["note"] = "Response body truncated to 2000 characters."

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


# Dispatch table
TOOL_DISPATCH = {
    "run_shell_command": run_shell_command,
    "execute_python": execute_python,
    "write_file": write_file,
    "read_file": read_file,
    "http_request": http_request,
    "install_python_package": install_python_package,
    "run_playwright_script": run_playwright_script,
}
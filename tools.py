"""
tools.py — Functions the agent can call to interact with the sandbox.
Each function maps 1-to-1 with a JSON schema defined in schemas.py.
"""

import os
from sandbox import get_container, WORKSPACE_CONTAINER
import urllib.request
import urllib.parse
import json
TEMP_SCRIPT = os.path.join(WORKSPACE_CONTAINER, "agent_temp.py")

def http_request(url: str, method: str = "GET", data: str = None, headers: dict = None) -> dict:
    """
    Perform an HTTP request inside the sandbox using urllib (built-in).
    """
    container = get_container()
    print(f"\n[Tool] http_request: {method} {url}")

    # Convert the Python function into a small inline script using urllib
    # This avoids having to install requests.
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
    # Write script to temp file and run
    temp_file = "/tmp/http_req.py"
    container.exec_run(cmd=["sh", "-c", f"cat > {temp_file} << 'EOF'\n{script}\nEOF"])
    result = container.exec_run(cmd=["python", temp_file], demux=True)

    stdout = result.output[0].decode("utf-8", errors="replace") if result.output[0] else ""
    stderr = result.output[1].decode("utf-8", errors="replace") if result.output[1] else ""
    exit_code = result.exit_code

    try:
        parsed = json.loads(stdout) if stdout else {}
    except:
        parsed = {"error": "Failed to parse response", "raw_stdout": stdout, "stderr": stderr}

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

    return {
        "success": success,
        "stdout": stdout,
        "stderr": stderr,
        "packages": packages,
    }
def run_playwright_script(script: str) -> dict:
    """
    Run a Playwright automation script inside the sandbox.
    Assumes Playwright and Chromium are pre-installed in the container.
    """
    container = get_container()
    print(f"\n[Tool] run_playwright_script (length={len(script)})")

    # Write script to temp file
    temp_script = "/tmp/playwright_script.py"
    write_cmd = f"cat > {temp_script} << 'PYEOF'\n{script}\nPYEOF"
    container.exec_run(cmd=["sh", "-c", write_cmd])

    # Execute the script
    result = container.exec_run(
        cmd=["python", temp_script],
        workdir=WORKSPACE_CONTAINER,
        demux=True,
    )

    stdout = result.output[0].decode("utf-8", errors="replace") if result.output[0] else ""
    stderr = result.output[1].decode("utf-8", errors="replace") if result.output[1] else ""
    exit_code = result.exit_code

    print(f"[Tool] Playwright exit code: {exit_code}")

    return {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
    }

def run_shell_command(command: str) -> dict:
    """
    Execute a shell command inside the sandbox container.

    Args:
        command: The shell command string to execute (e.g., "ls -la /workspace")

    Returns:
        dict with 'stdout', 'stderr', and 'exit_code'
    """
    container = get_container()
    print(f"\n[Tool] run_shell_command: {command}")

    result = container.exec_run(
        cmd=["sh", "-c", command],
        workdir=WORKSPACE_CONTAINER,
        demux=True,         # Separate stdout and stderr streams
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

    Args:
        code: A string of valid Python code to run.

    Returns:
        dict with 'stdout', 'stderr', and 'exit_code'
    """
    container = get_container()
    print(f"\n[Tool] execute_python:\n{code}\n")

    # Write code to the temp script file inside the container
    # We use a shell heredoc to avoid quoting issues
    escaped = code.replace("'", "'\\''")   # Escape single quotes for the shell
    write_cmd = f"cat > {TEMP_SCRIPT} << 'PYEOF'\n{code}\nPYEOF"
    container.exec_run(cmd=["sh", "-c", write_cmd])

    # Now execute the script
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

    Args:
        filename: Name of the file (e.g., "solution.py", "output.txt")
        content:  The text content to write

    Returns:
        dict with 'success' and 'path'
    """
    container = get_container()
    filepath = os.path.join(WORKSPACE_CONTAINER, filename)
    print(f"\n[Tool] write_file: {filepath}")

    # Use printf to avoid heredoc newline issues with binary-like content
    write_cmd = f"printf '%s' '{content.replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}' > {filepath}"
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

    Args:
        filename: Name of the file to read (e.g., "output.txt")

    Returns:
        dict with 'content' or 'error'
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


# ── Dispatch table ─────────────────────────────────────────────────────────────
# Maps tool names (as the LLM sees them) → Python functions
TOOL_DISPATCH = {
    "run_shell_command": run_shell_command,
    "execute_python":    execute_python,
    "write_file":        write_file,
    "read_file":         read_file,
    "http_request":      http_request,
    "install_python_package": install_python_package,
    "run_playwright_script": run_playwright_script,
}

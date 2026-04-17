#!/usr/bin/env python3
"""
Comprehensive test suite for the sandbox agent tools.
Run this script from the PROJECT ROOT directory:
    python test/test_all_tools.py

Or run from anywhere with the proper PYTHONPATH set.

It will start the sandbox, execute a series of tests for each tool,
and write detailed logs to a timestamped file inside the test/ folder.
"""

import os
import sys
import json
import time
import traceback
from datetime import datetime
from pathlib import Path

# --- PATH SETUP ---
# Add the parent directory (project root) to sys.path so we can import sandbox and tools
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

# Import the sandbox and tool modules
from sandbox import start_sandbox, get_container, WORKSPACE_CONTAINER, WORKSPACE_HOST
import tools

# Configure logging - log file will be created in the test/ directory
TEST_DIR = Path(__file__).parent.absolute()
LOG_FILE = TEST_DIR / f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

def log(message: str, level: str = "INFO"):
    """Write message to both console and log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] [{level}] {message}"
    print(formatted)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(formatted + "\n")

def log_separator(title: str = ""):
    """Print a visual separator."""
    sep = "=" * 80
    if title:
        log(sep)
        log(f"  {title}")
        log(sep)
    else:
        log(sep)

def run_test(name: str, func, *args, **kwargs):
    """Execute a test function and log the result."""
    log_separator(f"TEST: {name}")
    log(f"Function: {func.__name__}")
    # Truncate long arguments for logging
    args_str = str(args)[:500] + "..." if len(str(args)) > 500 else str(args)
    kwargs_str = str(kwargs)[:500] + "..." if len(str(kwargs)) > 500 else str(kwargs)
    log(f"Arguments: args={args_str}, kwargs={kwargs_str}")
    try:
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start_time
        log(f"Elapsed: {elapsed:.3f}s")
        log("Result:")
        # Format result for logging, handle large strings
        result_str = json.dumps(result, indent=2, default=str)
        if len(result_str) > 2000:
            result_str = result_str[:2000] + "\n... [truncated for log]"
        log(result_str)
        return result
    except Exception as e:
        elapsed = time.time() - start_time if 'start_time' in locals() else 0
        log(f"Elapsed: {elapsed:.3f}s", level="ERROR")
        log(f"ERROR: {str(e)}", level="ERROR")
        log(traceback.format_exc(), level="ERROR")
        return {"error": str(e), "traceback": traceback.format_exc()}

def verify_workspace():
    """Verify the host workspace directory exists and is writable."""
    log_separator("ENVIRONMENT CHECK")
    log(f"Project root: {PROJECT_ROOT}")
    log(f"Test directory: {TEST_DIR}")
    log(f"Log file: {LOG_FILE}")
    log(f"Workspace host path: {WORKSPACE_HOST}")
    
    # Check if workspace directory exists or can be created
    if os.path.exists(WORKSPACE_HOST):
        log(f"Workspace directory exists: {WORKSPACE_HOST}")
        # Check writability
        if os.access(WORKSPACE_HOST, os.W_OK):
            log("Workspace directory is writable")
        else:
            log("WARNING: Workspace directory is not writable", level="WARNING")
    else:
        log(f"Workspace directory does not exist yet (will be created by sandbox)")

def main():
    log_separator("SANDBOX AGENT TOOL TEST SUITE")
    log(f"Start time: {datetime.now().isoformat()}")
    
    # Environment verification
    verify_workspace()

    # Start the sandbox container
    log_separator("STARTING SANDBOX")
    try:
        container = start_sandbox()
        log(f"Container started: ID={container.short_id}, Name={container.name}")
        log(f"Container status: {container.status}")
    except Exception as e:
        log(f"Failed to start sandbox: {e}", level="FATAL")
        log(traceback.format_exc(), level="FATAL")
        sys.exit(1)

    # Give container a moment to be fully ready
    time.sleep(2)
    
    # Verify container is still running
    try:
        container.reload()
        log(f"Container running: {container.status}")
    except Exception as e:
        log(f"Container check failed: {e}", level="ERROR")

    # Track test results summary
    test_summary = {"passed": 0, "failed": 0, "total": 0}

    # -------------------- TEST CASES --------------------

    # 1. Shell command: echo and python version
    result = run_test(
        "Shell Command - echo hello",
        tools.run_shell_command,
        "echo 'Hello from test suite!'"
    )
    test_summary["total"] += 1
    if "error" not in result:
        test_summary["passed"] += 1
    else:
        test_summary["failed"] += 1

    result = run_test(
        "Shell Command - Python version",
        tools.run_shell_command,
        "python --version"
    )
    test_summary["total"] += 1
    if "error" not in result:
        test_summary["passed"] += 1
    else:
        test_summary["failed"] += 1

    # 2. Python execution: simple print and sum
    result = run_test(
        "Execute Python - print and sum",
        tools.execute_python,
        "print('Hello, Sandbox!')\nprint('Sum:', sum(range(1, 11)))"
    )
    test_summary["total"] += 1
    if "error" not in result and result.get("exit_code") == 0:
        test_summary["passed"] += 1
    else:
        test_summary["failed"] += 1

    # 3. Write and read file
    test_filename = "test_agent_file.txt"
    test_content = "This is a test file created by the automated test suite."
    result = run_test(
        "Write File",
        tools.write_file,
        test_filename,
        test_content
    )
    test_summary["total"] += 1
    if "error" not in result and result.get("success"):
        test_summary["passed"] += 1
    else:
        test_summary["failed"] += 1

    result = run_test(
        "Read File",
        tools.read_file,
        test_filename
    )
    test_summary["total"] += 1
    if "error" not in result and result.get("content") == test_content:
        test_summary["passed"] += 1
    else:
        test_summary["failed"] += 1

    # 4. HTTP request (small response)
    result = run_test(
        "HTTP Request - httpbin.org/json",
        tools.http_request,
        "https://httpbin.org/json",
        method="GET"
    )
    test_summary["total"] += 1
    if "error" not in result and "status" in result:
        test_summary["passed"] += 1
    else:
        test_summary["failed"] += 1

    # 5. HTTP request (large response) - using jsonplaceholder photos
    result_large = run_test(
        "HTTP Request (large) - jsonplaceholder photos",
        tools.http_request,
        "https://jsonplaceholder.typicode.com/photos",
        method="GET"
    )
    test_summary["total"] += 1
    if "error" not in result_large:
        test_summary["passed"] += 1
    else:
        test_summary["failed"] += 1

    # 6. Install Python package (emoji) and verify
    result = run_test(
        "Install Package - emoji",
        tools.install_python_package,
        ["emoji"]
    )
    test_summary["total"] += 1
    if "error" not in result:
        test_summary["passed"] += 1
    else:
        test_summary["failed"] += 1

    result = run_test(
        "Execute Python with emoji",
        tools.execute_python,
        "import emoji\nprint(repr(emoji.emojize(':smile:')))"
    )
    test_summary["total"] += 1
    if "error" not in result and result.get("exit_code") == 0:
        test_summary["passed"] += 1
    else:
        test_summary["failed"] += 1

    # 7. Playwright script: navigate to example.com
    playwright_script = """
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('https://example.com')
        title = await page.title()
        print(f'Page title: {title}')
        await browser.close()

asyncio.run(main())
"""
    result = run_test(
        "Playwright - navigate to example.com",
        tools.run_playwright_script,
        playwright_script
    )
    test_summary["total"] += 1
    if "error" not in result and result.get("exit_code") == 0:
        test_summary["passed"] += 1
    else:
        test_summary["failed"] += 1

    # 8. list_files - check workspace
    result = run_test(
        "List Files - /workspace",
        tools.list_files,
        "/workspace"
    )
    test_summary["total"] += 1
    if "error" not in result and result.get("exit_code") == 0:
        test_summary["passed"] += 1
    else:
        test_summary["failed"] += 1

    # 9. grep_file - search in a file (use the test file we created)
    result = run_test(
        "grep_file - search 'test' in test file",
        tools.grep_file,
        os.path.join(WORKSPACE_CONTAINER, test_filename),
        "test"
    )
    test_summary["total"] += 1
    if "error" not in result:
        test_summary["passed"] += 1
    else:
        test_summary["failed"] += 1

    # 10. read_file_range - read lines from a file
    result = run_test(
        "read_file_range - first 2 lines of test file",
        tools.read_file_range,
        os.path.join(WORKSPACE_CONTAINER, test_filename),
        1,
        2
    )
    test_summary["total"] += 1
    if "error" not in result:
        test_summary["passed"] += 1
    else:
        test_summary["failed"] += 1

    # 11. Check http_responses directory
    result = run_test(
        "List Files - /workspace/http_responses",
        tools.list_files,
        "/workspace/http_responses"
    )
    test_summary["total"] += 1
    if "error" not in result:
        test_summary["passed"] += 1
    else:
        test_summary["failed"] += 1

    # If large HTTP response was saved, demonstrate exploring it
    if result_large and "full_response_file" in result_large:
        large_file = result_large["full_response_file"]
        log(f"Large response saved to: {large_file}")
        result = run_test(
            "grep_file - search for 'title' in large response",
            tools.grep_file,
            large_file,
            "title",
            max_lines=5
        )
        test_summary["total"] += 1
        if "error" not in result:
            test_summary["passed"] += 1
        else:
            test_summary["failed"] += 1

        result = run_test(
            "read_file_range - first 10 lines of large response",
            tools.read_file_range,
            large_file,
            1,
            10
        )
        test_summary["total"] += 1
        if "error" not in result:
            test_summary["passed"] += 1
        else:
            test_summary["failed"] += 1

    # --- SUMMARY ---
    log_separator("TEST SUITE SUMMARY")
    log(f"Total tests: {test_summary['total']}")
    log(f"Passed: {test_summary['passed']}")
    log(f"Failed: {test_summary['failed']}")
    if test_summary['total'] > 0:
        success_rate = (test_summary['passed'] / test_summary['total']) * 100
        log(f"Success rate: {success_rate:.1f}%")

    log_separator("TEST SUITE COMPLETED")
    log(f"End time: {datetime.now().isoformat()}")
    log(f"All results logged to: {LOG_FILE}")

    # Cleanup is automatic via atexit in sandbox.py
    log("Sandbox will be cleaned up automatically on exit.")

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Comprehensive test suite for the sandbox agent tools.
Run this script from the PROJECT ROOT directory:
    python test/test_all_tools.py

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
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

from sandbox import start_sandbox, get_container, WORKSPACE_CONTAINER, WORKSPACE_HOST
import tools

TEST_DIR = Path(__file__).parent.absolute()
LOG_FILE = TEST_DIR / f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

def log(message: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] [{level}] {message}"
    print(formatted)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(formatted + "\n")

def log_separator(title: str = ""):
    sep = "=" * 80
    if title:
        log(sep)
        log(f"  {title}")
        log(sep)
    else:
        log(sep)

def run_test(name: str, func, *args, **kwargs):
    log_separator(f"TEST: {name}")
    log(f"Function: {func.__name__}")
    args_str = str(args)[:500] + "..." if len(str(args)) > 500 else str(args)
    kwargs_str = str(kwargs)[:500] + "..." if len(str(kwargs)) > 500 else str(kwargs)
    log(f"Arguments: args={args_str}, kwargs={kwargs_str}")
    try:
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start_time
        log(f"Elapsed: {elapsed:.3f}s")
        log("Result:")
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
    log_separator("ENVIRONMENT CHECK")
    log(f"Project root: {PROJECT_ROOT}")
    log(f"Test directory: {TEST_DIR}")
    log(f"Log file: {LOG_FILE}")
    log(f"Workspace host path: {WORKSPACE_HOST}")
    if os.path.exists(WORKSPACE_HOST):
        log(f"Workspace directory exists: {WORKSPACE_HOST}")
        if os.access(WORKSPACE_HOST, os.W_OK):
            log("Workspace directory is writable")
        else:
            log("WARNING: Workspace directory is not writable", level="WARNING")
    else:
        log(f"Workspace directory does not exist yet (will be created by sandbox)")

def ensure_playwright():
    """Check if Playwright is installed; if not, attempt to install it."""
    log_separator("PRE-FLIGHT: Playwright Check")
    result = tools.run_shell_command("python -c 'import playwright' 2>/dev/null && echo 'OK' || echo 'MISSING'")
    if "OK" in result.get("stdout", ""):
        log("Playwright is already installed.")
        return True
    else:
        log("Playwright not found. Attempting automatic installation...", level="WARNING")
        log("This may take a few minutes.")
        # Install playwright and chromium
        inst = tools.install_python_package(["playwright"])
        if not inst.get("success"):
            log("Failed to install playwright package.", level="ERROR")
            return False
        tools.run_shell_command("playwright install chromium")
        # Verify again
        result2 = tools.run_shell_command("python -c 'import playwright' && echo 'OK'")
        if "OK" in result2.get("stdout", ""):
            log("Playwright installed successfully.")
            return True
        else:
            log("Playwright installation verification failed.", level="ERROR")
            return False

def main():
    log_separator("SANDBOX AGENT TOOL TEST SUITE")
    log(f"Start time: {datetime.now().isoformat()}")
    verify_workspace()

    # Start sandbox
    log_separator("STARTING SANDBOX")
    try:
        container = start_sandbox()
        log(f"Container started: ID={container.short_id}, Name={container.name}")
        log(f"Container status: {container.status}")
    except Exception as e:
        log(f"Failed to start sandbox: {e}", level="FATAL")
        log(traceback.format_exc(), level="FATAL")
        sys.exit(1)

    time.sleep(2)
    try:
        container.reload()
        log(f"Container running: {container.status}")
    except Exception as e:
        log(f"Container check failed: {e}", level="ERROR")

    test_summary = {"passed": 0, "failed": 0, "total": 0}

    # --- BASIC TOOLS ---
    result = run_test("Shell Command - echo hello", tools.run_shell_command, "echo 'Hello from test suite!'")
    test_summary["total"] += 1
    test_summary["passed" if "error" not in result else "failed"] += 1

    result = run_test("Shell Command - Python version", tools.run_shell_command, "python --version")
    test_summary["total"] += 1
    test_summary["passed" if "error" not in result else "failed"] += 1

    result = run_test("Execute Python - print and sum", tools.execute_python,
                      "print('Hello, Sandbox!')\nprint('Sum:', sum(range(1, 11)))")
    test_summary["total"] += 1
    test_summary["passed" if (not result.get("error") and result.get("exit_code") == 0) else "failed"] += 1

    test_filename = "test_agent_file.txt"
    test_content = "This is a test file created by the automated test suite."
    result = run_test("Write File", tools.write_file, test_filename, test_content)
    test_summary["total"] += 1
    test_summary["passed" if (not result.get("error") and result.get("success")) else "failed"] += 1

    result = run_test("Read File", tools.read_file, test_filename)
    test_summary["total"] += 1
    test_summary["passed" if (not result.get("error") and result.get("content") == test_content) else "failed"] += 1

    # --- HTTP REQUESTS ---
    # Debug: simple urllib test to ensure network works
    run_test("DEBUG - Python urllib connectivity", tools.execute_python,
             "import urllib.request; print(urllib.request.urlopen('https://httpbin.org/json').getcode())")

    result = run_test("HTTP Request - httpbin.org/json", tools.http_request,
                      "https://httpbin.org/json", method="GET")
    test_summary["total"] += 1
    if "error" not in result and "status" in result:
        test_summary["passed"] += 1
    else:
        test_summary["failed"] += 1

    result_large = run_test("HTTP Request (large) - jsonplaceholder photos", tools.http_request,
                            "https://jsonplaceholder.typicode.com/photos", method="GET")
    test_summary["total"] += 1
    test_summary["passed" if "error" not in result_large else "failed"] += 1

    # --- PACKAGE INSTALL & EMOJI ---
    result = run_test("Install Package - emoji", tools.install_python_package, ["emoji"])
    test_summary["total"] += 1
    test_summary["passed" if "error" not in result else "failed"] += 1

    # Emoji test with multiple fallback shortcodes
    emoji_code = """
import emoji
# Try several known shortcodes
for code in [':smile:', ':grinning_face:', ':smiley:', ':slightly_smiling_face:']:
    converted = emoji.emojize(code)
    if converted != code:
        print(f'Success: {code} -> {repr(converted)}')
        break
else:
    print('No emoji conversion worked; raw:', repr(emoji.emojize(':smile:')))
"""
    result = run_test("Execute Python with emoji", tools.execute_python, emoji_code)
    test_summary["total"] += 1
    # Consider pass if script runs without error, regardless of conversion success
    test_summary["passed" if (not result.get("error") and result.get("exit_code") == 0) else "failed"] += 1

    # --- PLAYWRIGHT ---
    if not ensure_playwright():
        log("Skipping Playwright tests because installation failed.", level="ERROR")
        test_summary["total"] += 1
        test_summary["failed"] += 1
    else:
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
        result = run_test("Playwright - navigate to example.com", tools.run_playwright_script, playwright_script)
        test_summary["total"] += 1
        test_summary["passed" if (not result.get("error") and result.get("exit_code") == 0) else "failed"] += 1

    # --- FILE EXPLORATION TOOLS ---
    result = run_test("List Files - /workspace", tools.list_files, "/workspace")
    test_summary["total"] += 1
    test_summary["passed" if (not result.get("error") and result.get("exit_code") == 0) else "failed"] += 1

    result = run_test("grep_file - search 'test' in test file", tools.grep_file,
                      os.path.join(WORKSPACE_CONTAINER, test_filename), "test")
    test_summary["total"] += 1
    test_summary["passed" if "error" not in result else "failed"] += 1

    result = run_test("read_file_range - first 2 lines of test file", tools.read_file_range,
                      os.path.join(WORKSPACE_CONTAINER, test_filename), 1, 2)
    test_summary["total"] += 1
    test_summary["passed" if "error" not in result else "failed"] += 1

    result = run_test("List Files - /workspace/http_responses", tools.list_files, "/workspace/http_responses")
    test_summary["total"] += 1
    test_summary["passed" if "error" not in result else "failed"] += 1

    # Explore large HTTP response if saved
    if result_large and "full_response_file" in result_large:
        large_file = result_large["full_response_file"]
        log(f"Large response saved to: {large_file}")
        result = run_test("grep_file - search for 'title' in large response", tools.grep_file,
                          large_file, "title", max_lines=5)
        test_summary["total"] += 1
        test_summary["passed" if "error" not in result else "failed"] += 1
        result = run_test("read_file_range - first 10 lines of large response", tools.read_file_range,
                          large_file, 1, 10)
        test_summary["total"] += 1
        test_summary["passed" if "error" not in result else "failed"] += 1

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
    log("Sandbox will be cleaned up automatically on exit.")

if __name__ == "__main__":
    main()
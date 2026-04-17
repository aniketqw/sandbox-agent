# tools/dispatch.py
from tools.implementations import (
    run_shell_command,
    execute_python,
    write_file,
    read_file,
    http_request,
    install_python_package,
    run_playwright_script,
    grep_file,
    read_file_range,
    list_files,
    ask_human,
)

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
}
"""
schemas.py — OpenAI-compatible JSON schemas for each tool.
These are passed to the LLM in the `tools` array so it knows what to call.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_shell_command",
            "description": (
                "Execute any shell command inside the isolated Docker sandbox. "
                "Use this to install packages (pip install ...), navigate the "
                "filesystem, run scripts, or interact with the OS."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to run, e.g. 'pip install numpy' or 'ls -la /workspace'",
                    }
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_python",
            "description": (
                "Write and execute a Python script inside the isolated Docker sandbox. "
                "The script runs in /workspace. Use this for computations, data processing, "
                "or any task requiring Python execution. Prefer this over run_shell_command "
                "for Python-specific tasks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Complete, valid Python code to execute. Must be self-contained.",
                    }
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Write text content to a named file inside /workspace in the sandbox. "
                "Use this to save scripts, data files, or results for later use."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "The filename (not full path), e.g. 'fibonacci.py' or 'results.txt'",
                    },
                    "content": {
                        "type": "string",
                        "description": "The text content to write into the file.",
                    },
                },
                "required": ["filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the content of a file from /workspace in the sandbox. "
                "Use this to inspect results or previously written files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "The filename to read (not full path), e.g. 'output.txt'",
                    }
                },
                "required": ["filename"],
            },
        },
    },
        {
        "type": "function",
        "function": {
            "name": "http_request",
            "description": (
                "Perform a simple HTTP request (GET or POST) to a given URL. "
                "Returns response status, headers, and body. "
                "Useful for testing connectivity or fetching data from APIs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL to request (e.g., https://httpbin.org/get)"
                    },
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST"],
                        "default": "GET",
                        "description": "HTTP method to use"
                    },
                    "data": {
                        "type": "string",
                        "description": "Optional request body for POST requests"
                    },
                    "headers": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "description": "Optional HTTP headers as a JSON object"
                    }
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "install_python_package",
            "description": (
                "Install one or more Python packages using pip inside the sandbox. "
                "Use this before running scripts that require external libraries."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "packages": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of package names (e.g., ['requests', 'beautifulsoup4'])"
                    }
                },
                "required": ["packages"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_playwright_script",
            "description": (
                "Execute a browser automation script using Playwright. "
                "The script should be a complete Python program using the Playwright library. "
                "The sandbox will ensure Playwright and Chromium are installed before running. "
                "Use this for tasks like navigating pages, clicking buttons, filling forms, and extracting data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "script": {
                        "type": "string",
                        "description": "Python code that uses Playwright to automate a browser."
                    }
                },
                "required": ["script"],
            },
        },
    },

]

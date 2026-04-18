"""
sandbox.py — Manages the Docker container lifecycle.
Spins up a sandboxed Python container with internet access and tears it down cleanly.
"""

import docker
import os
import atexit

WORKSPACE_HOST = os.path.join(os.path.dirname(__file__), "agent_workspace")
WORKSPACE_CONTAINER = "/workspace"
IMAGE = "mcr.microsoft.com/playwright/python:v1.47.0-noble"  # verified working tag
CONTAINER_NAME = "sandbox_agent_env"

# Use explicit socket path for Docker Desktop on macOS
client = docker.DockerClient(base_url='unix:///Users/aniketsaxena/.docker/run/docker.sock')
_container = None

def start_sandbox():
    global _container
    try:
        old = client.containers.get(CONTAINER_NAME)
        print(f"[Sandbox] Removing stale container '{CONTAINER_NAME}'...")
        old.stop()
        old.remove()
    except docker.errors.NotFound:
        pass

    os.makedirs(WORKSPACE_HOST, exist_ok=True)

    print(f"[Sandbox] Starting container '{CONTAINER_NAME}'...")
    _container = client.containers.run(
        image=IMAGE,
        name=CONTAINER_NAME,
        command="tail -f /dev/null",
        detach=True,
        volumes={
            WORKSPACE_HOST: {
                "bind": WORKSPACE_CONTAINER,
                "mode": "rw",
            }
        },
        working_dir=WORKSPACE_CONTAINER,
        mem_limit="1g",
    )

    print(f"[Sandbox] Container '{CONTAINER_NAME}' is running (ID: {_container.short_id})")

    # Check Playwright with a quick import test
    print("[Sandbox] Checking Playwright...")
    check = _container.exec_run(["python", "-c", "import playwright"], demux=True)
    
    if check.exit_code != 0:
        print("[Sandbox] Playwright not found. Installing (this may take ~30 seconds)...")
        print("[Sandbox] Installing playwright package...")
        inst = _container.exec_run(["pip", "install", "playwright"], demux=True)
        if inst.exit_code != 0:
            stderr = inst.output[1].decode() if inst.output[1] else ""
            print(f"[Sandbox] Warning: Playwright pip install failed.\n{stderr}")
        else:
            stdout = inst.output[0].decode() if inst.output[0] else ""
            print(stdout)
            print("[Sandbox] Installing Chromium browser...")
            browser_inst = _container.exec_run(["playwright", "install", "chromium"], demux=True)
            if browser_inst.exit_code != 0:
                stderr = browser_inst.output[1].decode() if browser_inst.output[1] else ""
                print(f"[Sandbox] Warning: Chromium install failed.\n{stderr}")
            else:
                stdout = browser_inst.output[0].decode() if browser_inst.output[0] else ""
                print(stdout)
                print("[Sandbox] Playwright and Chromium installed successfully.")

    atexit.register(stop_sandbox)
    return _container

def stop_sandbox():
    global _container
    if _container:
        try:
            print(f"\n[Sandbox] Stopping container '{CONTAINER_NAME}'...")
            _container.stop(timeout=5)
            _container.remove()
            print(f"[Sandbox] Container removed. Goodbye.")
        except Exception as e:
            print(f"[Sandbox] Cleanup error (safe to ignore): {e}")
        finally:
            _container = None

def get_container():
    if _container is None:
        raise RuntimeError("Sandbox not started. Call start_sandbox() first.")
    return _container
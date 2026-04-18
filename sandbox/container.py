"""
sandbox.py — Manages the Docker container lifecycle.
Works locally (macOS) and inside LangGraph Studio.
"""

import docker
import os
import atexit

WORKSPACE_HOST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agent_workspace"))
WORKSPACE_CONTAINER = "/workspace"
IMAGE = "sandbox-agent:latest"

def _in_studio() -> bool:
    return os.getenv("LANGGRAPH_API_URL") is not None

def _get_docker_client():
    if _in_studio():
        # In Studio, we cannot connect to the host's Docker daemon.
        # Return None to indicate that Docker operations are unavailable.
        return None
    else:
        return docker.DockerClient(base_url="unix:///Users/aniketsaxena/.docker/run/docker.sock")

def _get_container_name():
    return "sandbox" if _in_studio() else "sandbox_agent_env"

client = _get_docker_client()
CONTAINER_NAME = _get_container_name()
_container = None
_persistent = os.getenv("SANDBOX_PERSISTENT", "true").lower() == "true"


def start_sandbox():
    global _container
    if client is None:
        print("[Sandbox] Running inside LangGraph Studio; assuming sandbox service is already running.")
        # Create a dummy container object for compatibility
        class DummyContainer:
            short_id = "studio-sandbox"
            status = "running"
            def exec_run(self, *args, **kwargs):
                raise NotImplementedError("Tool execution is not available in LangGraph Studio. Please run the agent locally (`python harness.py`) to execute tools.")
        _container = DummyContainer()
        return _container

    # ... rest of local logic unchanged ...


def stop_sandbox():
    global _container
    if _container:
        try:
            print(f"\n[Sandbox] Stopping container '{CONTAINER_NAME}'...")
            _container.stop(timeout=5)
            if not _persistent:
                _container.remove()
                print(f"[Sandbox] Container removed.")
            else:
                print(f"[Sandbox] Container stopped (persistent mode).")
        except Exception as e:
            print(f"[Sandbox] Cleanup error (safe to ignore): {e}")
        finally:
            if not _persistent:
                _container = None


def get_container():
    if _container is None:
        raise RuntimeError("Sandbox not started. Call start_sandbox() first.")
    return _container


def ensure_sandbox():
    """Idempotent function to ensure sandbox is running."""
    if _container is None or _container.status != "running":
        start_sandbox()
    return _container
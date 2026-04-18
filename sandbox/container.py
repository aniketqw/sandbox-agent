"""
sandbox.py — Manages the Docker container lifecycle.
Works locally (macOS) and inside LangGraph Studio (lazy client).
"""

import docker
import os
import atexit

WORKSPACE_HOST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agent_workspace"))
WORKSPACE_CONTAINER = "/workspace"
IMAGE = "sandbox-agent:latest"

def _in_studio() -> bool:
    return os.getenv("LANGGRAPH_API_URL") is not None

def _get_container_name():
    return "sandbox" if _in_studio() else "sandbox_agent_env"

_client = None
def _get_docker_client():
    global _client
    if _client is None:
        if _in_studio():
            socket_path = "/var/run/docker.sock"
        else:
            socket_path = "/Users/aniketsaxena/.docker/run/docker.sock"
        try:
            _client = docker.DockerClient(base_url=f"unix://{socket_path}")
            _client.ping()  # Verify connection
        except Exception as e:
            if _in_studio():
                raise RuntimeError(
                    f"Cannot connect to Docker in LangGraph Studio. "
                    f"Tool execution is only available when running locally (`python harness.py`)."
                )
            else:
                raise
    return _client

CONTAINER_NAME = _get_container_name()
_container = None
_persistent = os.getenv("SANDBOX_PERSISTENT", "true").lower() == "true"


def start_sandbox():
    global _container
    client = _get_docker_client()  # Lazy client creation

    try:
        existing = client.containers.get(CONTAINER_NAME)
        if existing.status == "running":
            print(f"[Sandbox] Reusing existing container '{CONTAINER_NAME}' (ID: {existing.short_id})")
            _container = existing
            return _container
        elif existing.status == "exited":
            print(f"[Sandbox] Starting stopped container '{CONTAINER_NAME}'...")
            existing.start()
            _container = existing
            print(f"[Sandbox] Container '{CONTAINER_NAME}' is running (ID: {_container.short_id})")
            return _container
        else:
            print(f"[Sandbox] Removing stale container '{CONTAINER_NAME}'...")
            existing.stop()
            existing.remove()
    except docker.errors.NotFound:
        pass

    os.makedirs(WORKSPACE_HOST, exist_ok=True)

    print(f"[Sandbox] Creating new container '{CONTAINER_NAME}'...")
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

    if not _persistent:
        atexit.register(stop_sandbox)

    return _container


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
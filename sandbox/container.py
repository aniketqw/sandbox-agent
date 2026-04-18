"""
sandbox.py — Manages the Docker container lifecycle.
Works locally (macOS) and inside LangGraph Studio.
Uses a persistent container that survives multiple runs.
"""

import docker
import os
import atexit

WORKSPACE_HOST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agent_workspace"))
WORKSPACE_CONTAINER = "/workspace"
IMAGE = "sandbox-agent:latest"

def _in_studio() -> bool:
    """Return True if running inside LangGraph Studio's container."""
    # LangGraph Studio sets LANGGRAPH_API_URL environment variable
    return os.getenv("LANGGRAPH_API_URL") is not None

def _get_docker_client():
    """Return a Docker client appropriate for the current environment."""
    if _in_studio():
        # Inside LangGraph Studio: use the mounted Docker socket
        return docker.DockerClient(base_url="unix:///var/run/docker.sock")
    else:
        # Local macOS: use Docker Desktop socket
        return docker.DockerClient(base_url="unix:///Users/aniketsaxena/.docker/run/docker.sock")

def _get_container_name():
    """Return the container name for the current environment."""
    return "sandbox" if _in_studio() else "sandbox_agent_env"

client = _get_docker_client()
CONTAINER_NAME = _get_container_name()
_container = None
_persistent = os.getenv("SANDBOX_PERSISTENT", "true").lower() == "true"


def start_sandbox():
    global _container

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
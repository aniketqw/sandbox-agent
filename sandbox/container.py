"""
sandbox.py — Manages the Docker container lifecycle.
Works locally (macOS) and inside LangGraph Studio.
Uses a persistent container that survives multiple runs.
"""

import docker
import os
import atexit

WORKSPACE_HOST = os.path.join(os.path.dirname(__file__), "agent_workspace")
WORKSPACE_CONTAINER = "/workspace"
IMAGE = "sandbox-agent:latest"

# Detect if running inside a container (LangGraph Studio)
IN_STUDIO = os.path.exists("/.dockerenv")

if IN_STUDIO:
    # Inside LangGraph Studio: use the Docker socket mounted in the studio container
    # The sandbox is a service defined in langgraph.json, accessible by name
    client = docker.DockerClient(base_url="unix:///var/run/docker.sock")
    CONTAINER_NAME = "sandbox"   # Matches the service name in langgraph.json
else:
    # Running locally on macOS: use the Docker Desktop socket
    client = docker.DockerClient(base_url="unix:///Users/aniketsaxena/.docker/run/docker.sock")
    CONTAINER_NAME = "sandbox_agent_env"

_container = None
_persistent = os.getenv("SANDBOX_PERSISTENT", "true").lower() == "true"


def start_sandbox():
    global _container

    # Check if container already exists
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

    # Only register cleanup if not persistent
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
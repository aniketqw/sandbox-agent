"""
sandbox.py — Manages the Docker container lifecycle.
Works locally (macOS) and safely degrades in LangGraph Studio.
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
            # In Studio, we don't create a real client.
            return None
        else:
            socket_path = "/Users/aniketsaxena/.docker/run/docker.sock"
            _client = docker.DockerClient(base_url=f"unix://{socket_path}")
    return _client

CONTAINER_NAME = _get_container_name()
_container = None
_persistent = os.getenv("SANDBOX_PERSISTENT", "true").lower() == "true"


def start_sandbox():
    global _container
    client = _get_docker_client()
    if client is None:
        print("[Sandbox] Running in LangGraph Studio – sandbox execution disabled.")
        # Return a dummy container object for compatibility
        class DummyContainer:
            short_id = "studio-dummy"
            status = "running"
            def exec_run(self, *args, **kwargs):
                print(f"[Sandbox] Would execute: {args}")
                # Return a dummy result that looks successful
                class DummyResult:
                    exit_code = 0
                    output = (b"", b"")
                return DummyResult()
        _container = DummyContainer()
        return _container

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
    if _container and not _in_studio():
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
"""TUI interface package for Aigent.

This package contains the Textual-based terminal user interface for Aigent,
including the main app and widget components.
"""

import asyncio
import sys
import uuid
from typing import Any

import httpx
from subprocess import Popen, DEVNULL

from aigent.interfaces.tui.app import AigentApp
from aigent.core.profiles import ProfileManager


async def check_server(url: str) -> bool:
    """Check if the server is running.

    Args:
        url: Base URL of the server to check.

    Returns:
        True if server is responding, False otherwise.
    """
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url)
            return resp.status_code == 200
        except Exception:
            return False


def start_server(host: str, port: int, yolo: bool) -> None:
    """Start the Aigent server in the background.

    Args:
        host: Host address to bind server to.
        port: Port number to bind server to.
        yolo: Whether to disable all permission checks.
    """
    print("Starting background server...")
    cmd = [sys.executable, "-m", "aigent.main", "serve", "--host", host, "--port", str(port)]
    if yolo:
        cmd.append("--yolo")
    Popen(cmd, stdout=DEVNULL, stderr=DEVNULL, start_new_session=True)


async def run_tui(args: Any) -> None:
    """Run the TUI interface.

    This is the main entry point for TUI mode. It:
    1. Connects to or starts the server
    2. Configures session and locking
    3. Launches the Textual TUI application

    Args:
        args: Parsed command-line arguments.
    """
    # Load configuration
    pm = ProfileManager()
    config = pm.config

    host = config.server.host
    port = config.server.port
    base_url = f"http://{host}:{port}"

    # Determine session ID and locking behavior
    should_lock = False
    if hasattr(args, "session") and args.session:
        session_id = args.session
        # No lock by default for named sessions in TUI
    else:
        session_id = f"tui-{uuid.uuid4().hex[:8]}"
        # No lock by default in TUI (can handle shared sessions)

    # Check for explicit --lock flag
    if hasattr(args, "lock") and args.lock:
        should_lock = True

    # Check for ephemeral flag
    ephemeral = False
    if hasattr(args, "ephemeral") and args.ephemeral:
        ephemeral = True

    # Generate unique user ID
    user_id = f"tui-{uuid.uuid4().hex[:8]}"
    ws_url = f"ws://{host}:{port}/ws/chat/{session_id}?profile={args.profile}&user_id={user_id}"

    # Check if we need to replace existing server
    if hasattr(args, "replace") and args.replace:
        from aigent.server.lifecycle import kill_server_process
        print("Replacing existing server...")
        kill_server_process(host=host, port=port)
        await asyncio.sleep(1)

    # Auto-start server if not running
    if not await check_server(base_url):
        start_server(host, port, args.yolo)
        # Wait for server to start
        for _ in range(10):
            await asyncio.sleep(1)
            if await check_server(base_url):
                break
        else:
            sys.stderr.write("Failed to start server.\n")
            return

    # Create and run app
    app = AigentApp(
        ws_url=ws_url,
        session_id=session_id,
        should_lock=should_lock,
        ephemeral=ephemeral,
        client_id=user_id,
        cursor_blink=config.tui.cursor_blink
    )
    await app.run_async()


__all__ = ["AigentApp", "run_tui"]

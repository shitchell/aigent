"""Interface Utilities.

Shared logic for CLI/TUI clients.
"""

import asyncio
import sys
import time
import httpx
from subprocess import Popen, DEVNULL

from aigent.core.logging import get_logger

logger = get_logger(__name__)

async def check_server(host: str, port: int) -> bool:
    url = f"http://{host}:{port}/"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, timeout=0.5)
            return resp.status_code == 200
        except Exception:
            return False

async def ensure_server(host: str, port: int) -> bool:
    """Check if server is running, if not start it."""
    if await check_server(host, port):
        return True
        
    print(f"Starting server at {host}:{port}...")
    
    # Spawn process
    # We use sys.executable to ensure we use the same venv
    cmd = [sys.executable, "-m", "aigent.main", "serve", "--host", host, "--port", str(port)]
    
    Popen(cmd, stdout=DEVNULL, stderr=DEVNULL, start_new_session=True)
    
    # Wait for startup
    for _ in range(20): # Wait up to 2 seconds
        if await check_server(host, port):
            return True
        await asyncio.sleep(0.1)
        
    print("Failed to start server.")
    return False

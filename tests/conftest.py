import pytest
import asyncio
import sys
import time
import socket
from contextlib import asynccontextmanager
from subprocess import Popen, DEVNULL
import websockets
import httpx

# Helper to find free port
def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

@pytest.fixture(scope="session")
def aigent_port():
    return get_free_port()

@pytest.fixture(scope="session")
async def aigent_server(aigent_port):
    """Spawns the server for E2E tests."""
    host = "127.0.0.1"
    port = aigent_port
    
    stdout_file = open("server_stdout.log", "w")
    stderr_file = open("server_stderr.log", "w")
    
    cmd = [sys.executable, "-m", "aigent.main", "serve", "--host", host, "--port", str(port)]
    proc = Popen(cmd, stdout=stdout_file, stderr=stderr_file)
    
    # Wait for health check
    url = f"http://{host}:{port}/"
    max_retries = 50
    for _ in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    break
        except:
            await asyncio.sleep(0.1)
    else:
        proc.kill()
        pytest.fail("Server failed to start")
        
    yield f"ws://{host}:{port}"
    
    proc.kill()

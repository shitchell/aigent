import pytest
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

def pytest_addoption(parser):
    parser.addoption(
        "--live", action="store_true", default=False, help="Run live API tests"
    )
    parser.addoption(
        "--e2e", action="store_true", default=False, help="Run E2E UI tests"
    )
    parser.addoption(
        "--run-e2e", action="store_true", default=False, help="Alias for --e2e"
    )

def pytest_collection_modifyitems(config, items):
    skip_live = pytest.mark.skip(reason="need --live option to run")
    skip_e2e = pytest.mark.skip(reason="need --e2e or --run-e2e option to run")

    for item in items:
        if "live" in item.keywords and not config.getoption("--live"):
            item.add_marker(skip_live)
        if "e2e" in item.keywords and not (config.getoption("--e2e") or config.getoption("--run-e2e")):
            item.add_marker(skip_e2e)


# Shared Fixtures

@pytest.fixture
def test_session_id():
    """Generate a unique test session ID."""
    import uuid
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture
async def test_server():
    """Start a test server instance."""
    import subprocess
    import httpx

    port = 18000  # Use non-standard port for tests
    proc = None

    try:
        # Start server
        proc = subprocess.Popen(
            [sys.executable, "-m", "aigent.main", "serve", "--port", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # Wait for server to be ready
        for _ in range(20):
            await asyncio.sleep(0.5)
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"http://localhost:{port}/")
                    if resp.status_code == 200:
                        break
            except:
                continue
        else:
            raise TimeoutError("Test server failed to start")

        yield f"http://localhost:{port}"

    finally:
        if proc:
            proc.terminate()
            proc.wait(timeout=5)

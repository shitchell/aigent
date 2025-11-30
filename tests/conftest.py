import pytest
import asyncio
import sys
import time
import socket
import tempfile
from pathlib import Path
from subprocess import Popen, PIPE
from unittest.mock import MagicMock, AsyncMock
import httpx

# Test configuration
TEST_PORT = 18765
TEST_HOST = "127.0.0.1"
TEST_PROFILE = "test"  # Dedicated test profile - avoids relying on "default"

# --- Server Fixtures ---

@pytest.fixture(scope="module")
def server():
    """Start aigent server for E2E tests."""
    proc = Popen(
        ["python", "-m", "aigent.main", "serve",
         "--host", TEST_HOST, "--port", str(TEST_PORT)],
        stdout=PIPE, stderr=PIPE
    )
    # Wait for startup
    for _ in range(30):
        try:
            resp = httpx.get(f"http://{TEST_HOST}:{TEST_PORT}/api/health", timeout=0.5)
            if resp.status_code == 200:
                break
        except:
            pass
        time.sleep(0.1)
    yield proc
    proc.terminate()
    proc.wait()

@pytest.fixture
def ws_url():
    return f"ws://{TEST_HOST}:{TEST_PORT}/ws/chat"

@pytest.fixture
def base_url():
    return f"http://{TEST_HOST}:{TEST_PORT}"

# --- Mock Fixtures ---

@pytest.fixture
def mock_bus():
    """Mock event bus for unit tests."""
    from aigent.core.events import Dispatcher
    bus = Dispatcher()
    return bus

@pytest.fixture
def test_profile():
    """Return the test profile name. Use this instead of hardcoding 'default'."""
    return TEST_PROFILE

@pytest.fixture
def mock_session():
    """Create a test session using the dedicated test profile."""
    from aigent.core.schemas import Session
    return Session(id="test-session", profile=TEST_PROFILE)

@pytest.fixture
def mock_user():
    """Create a test user."""
    from aigent.core.schemas import User, ClientType
    return User(id="test-user", name="Test User", client_type=ClientType.UNKNOWN)

@pytest.fixture
def mock_message():
    """Create a test message."""
    from aigent.core.schemas import Message, RoleType
    return Message(role=RoleType.USER, content="Test message")

# --- Temp Directory Fixtures ---

@pytest.fixture
def temp_session_dir():
    """Temporary directory for session storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

@pytest.fixture
def temp_crash_dir():
    """Temporary directory for crash dumps."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

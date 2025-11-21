import pytest
import asyncio
from aigent.server.api import ConnectionManager
from unittest.mock import MagicMock, AsyncMock

@pytest.mark.asyncio
async def test_shutdown_lifecycle():
    manager = ConnectionManager()
    manager.session_manager = MagicMock() 
    # Mock load_session to return None (awaitable)
    manager.session_manager.load_session = AsyncMock(return_value=None)
    # Mock replay_history
    manager.replay_history = AsyncMock()
    
    # 1. Connect
    ws = AsyncMock()
    await manager.connect(ws, "session-1")
    assert not manager.shutdown_task
    assert "session-1" in manager.active_connections
    
    # 2. Disconnect (Last one)
    manager.disconnect(ws, "session-1")
    assert manager.shutdown_task is not None
    
    # 3. Reconnect within grace period
    await manager.connect(ws, "session-1")
    assert manager.shutdown_task is None
    
    # 4. Disconnect again and wait (mock sleep not easy without freezegun, but we test logic state)
    manager.disconnect(ws, "session-1")
    assert manager.shutdown_task is not None
    # We won't wait 30s in unit test, but we verified the task was created.
    manager._cancel_shutdown_timer()

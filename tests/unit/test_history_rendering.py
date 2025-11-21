import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from aigent.server.api import ConnectionManager
from aigent.core.schemas import EventType
import json

@pytest.mark.asyncio
async def test_server_replays_history_as_snapshots():
    """
    Test that the server replays history using distinct events (e.g. HISTORY or TEXT)
    instead of streaming TOKEN events, to avoid CLI visual artifacts.
    """
    manager = ConnectionManager()
    manager.session_manager = MagicMock()
    
    # Mock Engine with History
    engine = MagicMock()
    engine.history = [
        HumanMessage(content="Hi"),
        AIMessage(content="Hello there")
    ]
    manager.sessions["test-session"] = engine
    
    # Mock WebSocket
    ws = AsyncMock()
    
    await manager.replay_history("test-session", ws)
    
    # Collect calls
    calls = [json.loads(c.args[0]) for c in ws.send_text.call_args_list]
    
    # We expect:
    # 1. USER_INPUT (Hi)
    # 2. HISTORY/SNAPSHOT (Hello there) -- NOT TOKEN
    
    assert calls[0]["type"] == EventType.USER_INPUT
    
    # This assertion should FAIL currently because code sends TOKEN
    print(f"Actual second event type: {calls[1]['type']}")
    assert calls[1]["type"] == "history_content", "Expected 'history_content' event, got token stream"

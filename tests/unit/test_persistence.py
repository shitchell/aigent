import pytest
import asyncio
from pathlib import Path
from langchain_core.messages import HumanMessage, AIMessage
from aigent.core.persistence import SessionManager

@pytest.mark.asyncio
async def test_save_and_load_session(tmp_path):
    # Setup
    manager = SessionManager(tmp_path)
    session_id = "test-session"
    profile_name = "default"
    history = [
        HumanMessage(content="Hello"),
        AIMessage(content="Hi there")
    ]

    # Save
    await manager.save_session(session_id, profile_name, history)
    
    # Verify file exists
    assert (tmp_path / "test-session.json").exists()

    # Load
    data = await manager.load_session(session_id)
    assert data is not None
    assert data["profile"] == profile_name
    assert len(data["history"]) == 2
    assert isinstance(data["history"][0], HumanMessage)
    assert data["history"][0].content == "Hello"

@pytest.mark.asyncio
async def test_list_sessions(tmp_path):
    manager = SessionManager(tmp_path)
    
    # Create dummy files
    (tmp_path / "a.json").touch()
    await asyncio.sleep(0.01) # Ensure mtime diff
    (tmp_path / "b.json").touch()
    
    sessions = manager.list_sessions()
    assert sessions == ["b", "a"] # Newest first

@pytest.mark.asyncio
async def test_load_nonexistent(tmp_path):
    manager = SessionManager(tmp_path)
    data = await manager.load_session("ghost")
    assert data is None

import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from aigent.server.api import ConnectionManager, SESSIONS_DIR
from langchain_core.messages import HumanMessage, AIMessage

@pytest.fixture
def mock_manager(tmp_path):
    # Patch the SESSIONS_DIR in the module to use tmp_path
    with patch("aigent.server.api.SESSIONS_DIR", tmp_path):
        cm = ConnectionManager()
        yield cm

@pytest.pytest.mark.asyncio
async def test_save_load_cycle(mock_manager):
    session_id = "test-session"
    
    # 1. Create a Mock Engine with History
    mock_engine = MagicMock()
    mock_engine.profile.name = "coder"
    mock_engine.history = [
        HumanMessage(content="Hi"),
        AIMessage(content="Hello")
    ]
    
    mock_manager.sessions[session_id] = mock_engine
    
    # 2. Save
    await mock_manager._save_session_to_disk(session_id)
    
    # Verify file exists
    # Note: We patched SESSIONS_DIR in the fixture context
    # But we need to access the *path* object used by the code.
    # Since we patched the global variable, simple file access works if we use the same path object.
    # Let's verify file content manually
    saved_file = list(patch.DEFAULT.glob("*.json")) 
    # Wait, patch.DEFAULT isn't right.
    # We passed tmp_path.
    
    files = list(mock_manager.SESSIONS_DIR.glob("*.json")) if hasattr(mock_manager, 'SESSIONS_DIR') else list(Path(patch("aigent.server.api.SESSIONS_DIR").new).glob("*.json"))
    
    # Actually, since we patched the module level variable, we can just check tmp_path
    expected_file = SESSIONS_DIR / f"{session_id}.json" 
    # Wait, SESSIONS_DIR is imported. Patching it *after* import requires patching where it is used.
    # In test_persistence.py, we imported SESSIONS_DIR.
    # Patching aigent.server.api.SESSIONS_DIR affects the code in api.py.
    # So checking tmp_path / f"{session_id}.json" is correct.
    
    # Re-implementation of test logic to be cleaner:
    
    pass

@pytest.pytest.mark.asyncio
async def test_persistence_logic(tmp_path):
    # We patch the GLOBAL constant in the module
    with patch("aigent.server.api.SESSIONS_DIR", tmp_path):
        cm = ConnectionManager()
        session_id = "persist-test"
        
        # Mock Engine
        mock_engine = MagicMock()
        mock_engine.profile.name = "cheap"
        mock_engine.history = [HumanMessage(content="Save me")]
        
        cm.sessions[session_id] = mock_engine
        
        # Save
        await cm._save_session_to_disk(session_id)
        
        expected_file = tmp_path / f"{session_id}.json"
        assert expected_file.exists()
        
        data = json.loads(expected_file.read_text())
        assert data["profile"] == "cheap"
        assert data["history"][0]["type"] == "human"
        assert data["history"][0]["data"]["content"] == "Save me"
        
        # Load
        # We need to mock ProfileManager and AgentEngine for hydration
        with patch("aigent.server.api.ProfileManager") as MockPM, \
             patch("aigent.server.api.AgentEngine") as MockEngineCls:
            
            MockEngineCls.return_value.initialize = AsyncMock()
            
            # Clear memory to force load
            cm.sessions = {}
            
            success = await cm._load_session_from_disk(session_id)
            
            assert success is True
            assert session_id in cm.sessions
            loaded_engine = cm.sessions[session_id]
            
            # Verify history restored
            assert len(loaded_engine.history) == 1
            assert loaded_engine.history[0].content == "Save me"

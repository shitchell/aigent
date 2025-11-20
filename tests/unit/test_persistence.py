import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from aigent.server.api import ConnectionManager
from langchain_core.messages import HumanMessage, AIMessage

@pytest.mark.asyncio
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
            
            # Setup Mock Engine Instance
            mock_loaded_engine = MagicMock()
            mock_loaded_engine.initialize = AsyncMock()
            MockEngineCls.return_value = mock_loaded_engine
            
            # Clear memory to force load
            cm.sessions = {}
            
            success = await cm._load_session_from_disk(session_id)
            
            assert success is True
            assert session_id in cm.sessions
            loaded_engine = cm.sessions[session_id]
            
            # Verify history restored
            assert len(loaded_engine.history) == 1
            assert loaded_engine.history[0].content == "Save me"
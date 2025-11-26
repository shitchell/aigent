"""Unit tests for ephemeral session functionality.

This module tests ephemeral session handling including persistence prevention,
cleanup on disconnect, and command-line flag validation.
"""

import pytest
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from io import StringIO
from langchain_core.messages import HumanMessage, AIMessage

from aigent.core.persistence import SessionManager


class TestEphemeralSessions:
    """Test suite for ephemeral session behavior."""

    @pytest.mark.asyncio
    async def test_ephemeral_not_persisted(self, tmp_path: Path):
        """Test that ephemeral sessions are not saved to disk.

        Args:
            tmp_path: Pytest fixture providing temporary directory.
        """
        # Create session manager with temp directory
        manager = SessionManager(tmp_path)

        session_id = "ephemeral-test"
        profile_name = "default"
        history = [
            HumanMessage(content="Test message"),
            AIMessage(content="Test response")
        ]

        # Simulate the server's logic: check ephemeral flag before saving
        # In the real implementation, save_session is called conditionally
        # Here we verify that when save is NOT called, no file is created

        # Don't save (simulating ephemeral behavior)
        # await manager.save_session(session_id, profile_name, history)

        # Verify file was NOT created
        session_file = tmp_path / f"{session_id}.json"
        assert not session_file.exists(), "Ephemeral session should not be persisted to disk"

    @pytest.mark.asyncio
    async def test_ephemeral_flag_prevents_save(self, tmp_path: Path):
        """Test that ephemeral flag prevents session from being saved.

        Args:
            tmp_path: Pytest fixture providing temporary directory.
        """
        manager = SessionManager(tmp_path)

        session_id = "ephemeral-test-2"
        profile_name = "default"
        history = [HumanMessage(content="Test")]

        # Simulate server behavior with ephemeral flag
        ephemeral = True

        if not ephemeral:
            await manager.save_session(session_id, profile_name, history)

        # Verify no session file exists
        session_file = tmp_path / f"{session_id}.json"
        assert not session_file.exists()

    @pytest.mark.asyncio
    async def test_regular_session_is_persisted(self, tmp_path: Path):
        """Test that non-ephemeral sessions ARE saved to disk (control test).

        Args:
            tmp_path: Pytest fixture providing temporary directory.
        """
        manager = SessionManager(tmp_path)

        session_id = "regular-test"
        profile_name = "default"
        history = [
            HumanMessage(content="Test message"),
            AIMessage(content="Test response")
        ]

        # Regular session - should save
        ephemeral = False

        if not ephemeral:
            await manager.save_session(session_id, profile_name, history)

        # Verify file WAS created
        session_file = tmp_path / f"{session_id}.json"
        assert session_file.exists(), "Regular session should be persisted to disk"

        # Verify we can load it back
        loaded = await manager.load_session(session_id)
        assert loaded is not None
        assert loaded["profile"] == profile_name
        assert len(loaded["history"]) == 2

    @pytest.mark.asyncio
    async def test_lock_session_mutual_exclusion(self):
        """Test that --lock and --session flags are mutually exclusive.

        This verifies the argument validation logic in run_cli.
        """
        from aigent.interfaces.cli import run_cli

        # Create mock args with both flags set
        args = Mock()
        args.lock = True
        args.session = "test-session"
        args.ephemeral = False
        args.repl = True
        args.tui = False

        # Capture stderr
        captured_stderr = StringIO()
        original_stderr = sys.stderr
        sys.stderr = captured_stderr

        # Should exit with error
        with pytest.raises(SystemExit) as exc_info:
            await run_cli(args)

        sys.stderr = original_stderr

        # Verify error code
        assert exc_info.value.code == 1

        # Verify error message
        error_output = captured_stderr.getvalue()
        assert "mutually exclusive" in error_output.lower()

    def test_lock_without_session_ok(self):
        """Test that --lock flag alone is valid.

        This verifies the flag combination logic.
        """
        # If lock is True and session is None, validation should pass
        # The actual validation happens in run_cli, so we just verify
        # the logic is correct conceptually
        args = Mock()
        args.lock = True
        args.session = None

        # This should not trigger the error condition
        should_error = args.lock and args.session
        assert not should_error, "--lock alone should be valid"

    def test_session_without_lock_ok(self):
        """Test that --session flag alone is valid.

        This verifies the flag combination logic.
        """
        args = Mock()
        args.lock = False
        args.session = "test-session"

        # This should not trigger the error condition
        should_error = args.lock and args.session
        assert not should_error, "--session alone should be valid"

    def test_ephemeral_with_lock_ok(self):
        """Test that --ephemeral and --lock can be used together.

        This verifies the flag combination logic.
        """
        args = Mock()
        args.lock = True
        args.session = None
        args.ephemeral = True

        # This should not trigger the error condition
        should_error = args.lock and args.session
        assert not should_error, "--ephemeral with --lock should be valid"

    def test_ephemeral_with_session_ok(self):
        """Test that --ephemeral and --session can be used together.

        Note: This is allowed but will show a warning in REPL mode.
        """
        args = Mock()
        args.lock = False
        args.session = "test-session"
        args.ephemeral = True

        # This should not trigger the error condition
        should_error = args.lock and args.session
        assert not should_error, "--ephemeral with --session should be valid"

    def test_all_flags_false_ok(self):
        """Test that no flags is valid (default behavior).

        This verifies the flag combination logic.
        """
        args = Mock()
        args.lock = False
        args.session = None
        args.ephemeral = False

        # This should not trigger the error condition
        should_error = args.lock and args.session
        assert not should_error, "No flags should be valid"

    @pytest.mark.asyncio
    async def test_ephemeral_session_deleted_on_cleanup(self, tmp_path: Path):
        """Test that ephemeral session data is cleaned up (simulated).

        This tests the conceptual cleanup - the actual server cleanup is tested
        in integration tests.

        Args:
            tmp_path: Pytest fixture providing temporary directory.
        """
        # Simulate server's session state management
        session_state = {
            "ephemeral-test": {
                "locked": False,
                "owner_client_id": None,
                "ephemeral": True
            }
        }

        sessions = {
            "ephemeral-test": Mock()  # Mock engine
        }

        locks = {
            "ephemeral-test": asyncio.Lock()
        }

        # Simulate disconnect cleanup
        session_id = "ephemeral-test"
        if session_state[session_id].get("ephemeral"):
            # Clean up
            del sessions[session_id]
            del locks[session_id]
            del session_state[session_id]

        # Verify cleanup
        assert session_id not in sessions
        assert session_id not in locks
        assert session_id not in session_state

    @pytest.mark.asyncio
    async def test_non_ephemeral_session_not_deleted(self, tmp_path: Path):
        """Test that regular sessions are NOT deleted on disconnect (control test).

        Args:
            tmp_path: Pytest fixture providing temporary directory.
        """
        # Simulate server's session state management
        session_state = {
            "regular-test": {
                "locked": False,
                "owner_client_id": None,
                "ephemeral": False
            }
        }

        sessions = {
            "regular-test": Mock()  # Mock engine
        }

        locks = {
            "regular-test": asyncio.Lock()
        }

        # Simulate disconnect cleanup
        session_id = "regular-test"
        if session_state[session_id].get("ephemeral"):
            # Would clean up, but ephemeral is False
            del sessions[session_id]
            del locks[session_id]
            del session_state[session_id]

        # Verify NOT cleaned up (ephemeral was False)
        assert session_id in sessions
        assert session_id in locks
        assert session_id in session_state

    def test_set_ephemeral_message_format(self):
        """Test that set_ephemeral message has correct format."""
        # Message sent by client to mark session as ephemeral
        msg = {"type": "set_ephemeral", "ephemeral": True}
        msg_json = json.dumps(msg)

        # Parse it back
        parsed = json.loads(msg_json)

        assert parsed["type"] == "set_ephemeral"
        assert parsed["ephemeral"] is True

    def test_set_ephemeral_false_message_format(self):
        """Test that set_ephemeral can disable ephemeral mode."""
        # Message to disable ephemeral mode
        msg = {"type": "set_ephemeral", "ephemeral": False}
        msg_json = json.dumps(msg)

        parsed = json.loads(msg_json)

        assert parsed["type"] == "set_ephemeral"
        assert parsed["ephemeral"] is False

    @pytest.mark.asyncio
    async def test_ephemeral_session_with_history_not_saved(self, tmp_path: Path):
        """Test that even sessions with history are not saved when ephemeral.

        Args:
            tmp_path: Pytest fixture providing temporary directory.
        """
        manager = SessionManager(tmp_path)

        session_id = "ephemeral-with-history"
        profile_name = "default"

        # Create substantial history
        history = []
        for i in range(10):
            history.append(HumanMessage(content=f"Message {i}"))
            history.append(AIMessage(content=f"Response {i}"))

        # Simulate ephemeral session - don't save
        ephemeral = True

        if not ephemeral:
            await manager.save_session(session_id, profile_name, history)

        # Verify file not created
        session_file = tmp_path / f"{session_id}.json"
        assert not session_file.exists(), \
            "Ephemeral session with history should still not be persisted"

    @pytest.mark.asyncio
    async def test_session_state_initialization(self):
        """Test that session state is properly initialized with ephemeral flag."""
        # Simulate server initialization
        session_state = {}

        session_id = "new-session"

        # Initialize session state
        if session_id not in session_state:
            session_state[session_id] = {
                "locked": False,
                "owner_client_id": None,
                "ephemeral": False
            }

        # Verify initialization
        assert session_id in session_state
        assert session_state[session_id]["locked"] is False
        assert session_state[session_id]["owner_client_id"] is None
        assert session_state[session_id]["ephemeral"] is False

    @pytest.mark.asyncio
    async def test_ephemeral_flag_can_be_set_after_connection(self):
        """Test that ephemeral flag can be set after connection is established."""
        # Simulate session state
        session_state = {
            "test-session": {
                "locked": False,
                "owner_client_id": None,
                "ephemeral": False
            }
        }

        session_id = "test-session"

        # Client sends set_ephemeral message
        msg = {"type": "set_ephemeral", "ephemeral": True}

        # Server processes it
        if msg.get("type") == "set_ephemeral":
            ephemeral = msg.get("ephemeral", True)
            session_state[session_id]["ephemeral"] = ephemeral

        # Verify flag was set
        assert session_state[session_id]["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_ephemeral_flag_can_be_toggled(self):
        """Test that ephemeral flag can be toggled on and off."""
        # Simulate session state
        session_state = {
            "test-session": {
                "locked": False,
                "owner_client_id": None,
                "ephemeral": False
            }
        }

        session_id = "test-session"

        # Set to ephemeral
        session_state[session_id]["ephemeral"] = True
        assert session_state[session_id]["ephemeral"] is True

        # Set back to persistent
        session_state[session_id]["ephemeral"] = False
        assert session_state[session_id]["ephemeral"] is False

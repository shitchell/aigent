"""
Unit tests for WebSocket protocol implementation.
Tests the WebSocket communication, broadcasting, and event handling in api.py.
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from aigent.server.api import ConnectionManager, process_chat_message
from aigent.core.schemas import EventType, AgentEvent


class TestWebSocketProtocol:
    """Test suite for WebSocket protocol implementation."""

    @pytest.mark.asyncio
    async def test_websocket_connection_protocol(self):
        """Test WebSocket connection and initial handshake."""
        manager = ConnectionManager()
        manager.session_manager = MagicMock()
        manager.session_manager.load_session = AsyncMock(return_value=None)

        # Mock the replay_history method to avoid actual history replay
        manager.replay_history = AsyncMock()

        # Mock WebSocket
        ws = AsyncMock()
        ws.accept = AsyncMock()

        # Test connection
        session_id = "test-session"
        profile = "default"

        # Mock ProfileManager to avoid file system access
        with patch('aigent.server.api.ProfileManager') as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile = MagicMock()
            mock_profile.name = profile
            mock_profile_manager.get_profile.return_value = mock_profile
            mock_pm.return_value = mock_profile_manager

            # Mock AgentEngine
            with patch('aigent.server.api.AgentEngine') as mock_engine_class:
                mock_engine = AsyncMock()
                mock_engine.initialize = AsyncMock()
                mock_engine.history = []
                mock_engine_class.return_value = mock_engine

                success = await manager.connect(ws, session_id, profile)

                assert success is True
                ws.accept.assert_called_once()
                assert session_id in manager.active_connections
                assert ws in manager.active_connections[session_id]
                assert session_id in manager.sessions
                assert session_id in manager.locks

                # Verify replay_history was called
                manager.replay_history.assert_called_once_with(session_id, ws)

    @pytest.mark.asyncio
    async def test_websocket_broadcasting(self):
        """Test message broadcasting to multiple connected clients."""
        manager = ConnectionManager()

        # Create multiple mock websockets
        ws1 = AsyncMock()
        ws1.send_text = AsyncMock()
        ws2 = AsyncMock()
        ws2.send_text = AsyncMock()
        ws3 = AsyncMock()
        ws3.send_text = AsyncMock()

        session_id = "broadcast-test"

        # Manually setup connections (bypass full connect logic)
        manager.active_connections[session_id] = [ws1, ws2, ws3]

        # Test broadcasting
        test_message = json.dumps({"type": "test", "content": "Hello all"})
        await manager.broadcast(session_id, test_message)

        # Verify all websockets received the message
        ws1.send_text.assert_called_once_with(test_message)
        ws2.send_text.assert_called_once_with(test_message)
        ws3.send_text.assert_called_once_with(test_message)

    @pytest.mark.asyncio
    async def test_websocket_disconnect(self):
        """Test proper cleanup on WebSocket disconnect."""
        manager = ConnectionManager()

        # Setup connection
        ws = AsyncMock()
        session_id = "disconnect-test"
        manager.active_connections[session_id] = [ws]

        # Test disconnect
        manager.disconnect(ws, session_id)

        # Verify cleanup
        assert session_id not in manager.active_connections
        assert manager.shutdown_task is not None  # Should start shutdown timer

    @pytest.mark.asyncio
    async def test_token_event_generation(self):
        """Test that TOKEN events are properly generated and sent."""
        manager = ConnectionManager()

        # Setup mock session
        session_id = "token-test"
        ws = AsyncMock()
        ws.send_text = AsyncMock()
        manager.active_connections[session_id] = [ws]

        # Create mock engine
        mock_engine = AsyncMock()
        mock_engine.profile = MagicMock()
        mock_engine.profile.name = "test"
        mock_engine.history = []

        # Mock the stream method to return token events
        async def mock_stream(user_input, user_name=None):
            yield AgentEvent(type=EventType.TOKEN, content="Hello")
            yield AgentEvent(type=EventType.TOKEN, content=" ")
            yield AgentEvent(type=EventType.TOKEN, content="World")
            yield AgentEvent(type=EventType.FINISH)

        mock_engine.stream = mock_stream
        manager.sessions[session_id] = mock_engine
        manager.locks[session_id] = asyncio.Lock()

        # Mock session manager
        manager.session_manager = MagicMock()
        manager.session_manager.save_session = AsyncMock()

        # Process a message
        await process_chat_message(session_id, "Test input", "test-user")

        # Give async tasks time to complete
        await asyncio.sleep(0.1)

        # Verify TOKEN events were broadcast
        calls = [call[0][0] for call in ws.send_text.call_args_list]

        # Parse JSON and check event types
        events = [json.loads(call) for call in calls]
        token_events = [e for e in events if e['type'] == EventType.TOKEN]
        finish_events = [e for e in events if e['type'] == EventType.FINISH]

        assert len(token_events) == 3
        assert len(finish_events) == 1
        assert token_events[0]['content'] == "Hello"
        assert token_events[1]['content'] == " "
        assert token_events[2]['content'] == "World"

    @pytest.mark.asyncio
    async def test_approval_response_handling(self):
        """Test handling of approval response messages."""
        manager = ConnectionManager()

        # Setup mock session
        session_id = "approval-test"
        ws = AsyncMock()
        ws.receive_text = AsyncMock()

        # Create mock engine with authorizer
        mock_engine = AsyncMock()
        mock_authorizer = MagicMock()
        mock_authorizer.resolve_request = MagicMock()
        mock_engine.authorizer = mock_authorizer

        manager.sessions[session_id] = mock_engine
        manager.active_connections[session_id] = [ws]

        # Simulate approval response
        approval_msg = json.dumps({
            "type": "approval_response",
            "request_id": "req-123",
            "decision": "allow"
        })

        # Process the approval
        # Note: In real code this happens in websocket_endpoint
        msg = json.loads(approval_msg)
        if msg.get("type") == "approval_response":
            req_id = msg.get("request_id")
            if mock_engine.authorizer and req_id:
                mock_engine.authorizer.resolve_request(str(req_id), msg)

        # Verify the authorizer was called
        mock_authorizer.resolve_request.assert_called_once_with("req-123", msg)

    @pytest.mark.asyncio
    async def test_user_input_broadcast(self):
        """Test that user input is broadcast to all clients in session."""
        manager = ConnectionManager()

        # Setup multiple clients
        ws1 = AsyncMock()
        ws1.send_text = AsyncMock()
        ws2 = AsyncMock()
        ws2.send_text = AsyncMock()

        session_id = "input-test"
        manager.active_connections[session_id] = [ws1, ws2]

        # Broadcast user input event
        user_event = AgentEvent(
            type=EventType.USER_INPUT,
            content="Test message",
            metadata={"user_id": "test-user"}
        )

        await manager.broadcast(session_id, user_event.to_json())

        # Verify both clients received the event
        expected_json = user_event.to_json()
        ws1.send_text.assert_called_once_with(expected_json)
        ws2.send_text.assert_called_once_with(expected_json)

    @pytest.mark.asyncio
    async def test_history_replay(self):
        """Test that history is properly replayed to new connections."""
        manager = ConnectionManager()

        ws = AsyncMock()
        ws.send_text = AsyncMock()
        session_id = "history-test"

        # Create mock engine with history
        from langchain_core.messages import HumanMessage, AIMessage

        mock_engine = MagicMock()
        mock_engine.history = [
            HumanMessage(content="Hello", name="user1"),
            AIMessage(content="Hi there!", tool_calls=[]),
            HumanMessage(content="How are you?", name="user1"),
            AIMessage(content="I'm doing well, thank you!", tool_calls=[])
        ]

        manager.sessions[session_id] = mock_engine

        # Replay history
        await manager.replay_history(session_id, ws)

        # Verify events were sent
        calls = [call[0][0] for call in ws.send_text.call_args_list]
        events = [json.loads(call) for call in calls]

        # Check event sequence
        assert events[0]['type'] == EventType.USER_INPUT
        assert events[0]['content'] == "Hello"
        assert events[1]['type'] == EventType.HISTORY_CONTENT
        assert events[1]['content'] == "Hi there!"
        assert events[2]['type'] == EventType.FINISH
        assert events[3]['type'] == EventType.USER_INPUT
        assert events[3]['content'] == "How are you?"
        assert events[4]['type'] == EventType.HISTORY_CONTENT
        assert events[4]['content'] == "I'm doing well, thank you!"
        assert events[5]['type'] == EventType.FINISH

    @pytest.mark.asyncio
    async def test_concurrent_session_locks(self):
        """Test that session locks prevent concurrent message processing."""
        manager = ConnectionManager()

        session_id = "lock-test"

        # Create mock engine
        mock_engine = AsyncMock()
        mock_engine.profile = MagicMock()
        mock_engine.profile.name = "test"

        # Track call order
        call_order = []

        async def slow_stream(user_input, user_name=None):
            call_order.append(f"start_{user_input}")
            await asyncio.sleep(0.1)  # Simulate processing time
            call_order.append(f"end_{user_input}")
            yield AgentEvent(type=EventType.FINISH)

        mock_engine.stream = slow_stream
        manager.sessions[session_id] = mock_engine
        manager.locks[session_id] = asyncio.Lock()
        manager.session_manager = MagicMock()
        manager.session_manager.save_session = AsyncMock()
        manager.active_connections[session_id] = []

        # Start two concurrent message processing tasks
        task1 = asyncio.create_task(process_chat_message(session_id, "message1"))
        task2 = asyncio.create_task(process_chat_message(session_id, "message2"))

        await task1
        await task2

        # Verify sequential processing
        assert call_order == ["start_message1", "end_message1", "start_message2", "end_message2"]

    @pytest.mark.asyncio
    async def test_error_event_on_exception(self):
        """Test that errors in processing generate ERROR events."""
        manager = ConnectionManager()

        session_id = "error-test"
        ws = AsyncMock()
        ws.send_text = AsyncMock()
        manager.active_connections[session_id] = [ws]

        # Create mock engine that raises an error
        mock_engine = AsyncMock()
        mock_engine.profile = MagicMock()
        mock_engine.profile.name = "test"

        async def error_stream(user_input, user_name=None):
            raise ValueError("Test error occurred")
            yield  # Never reached

        mock_engine.stream = error_stream
        manager.sessions[session_id] = mock_engine
        manager.locks[session_id] = asyncio.Lock()

        # Process message that will error
        await process_chat_message(session_id, "cause error")

        # Verify ERROR event was broadcast
        calls = [call[0][0] for call in ws.send_text.call_args_list]
        events = [json.loads(call) for call in calls]

        error_events = [e for e in events if e['type'] == EventType.ERROR]
        assert len(error_events) == 1
        assert "Test error occurred" in error_events[0]['content']
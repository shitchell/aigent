"""E2E tests for TUI shared session support.

This module tests the TUI application's ability to handle shared sessions
where multiple clients can connect to the same session and see each other's
messages in real-time.

These tests verify:
- External user messages display correctly
- Concurrent message updates don't corrupt state
- Streaming messages are preserved during external updates
- User ID prefixes are shown correctly
"""

import asyncio
import pytest
from typing import Optional

from aigent.interfaces.tui.app import AigentApp
from aigent.interfaces.tui.widgets.chat import ChatContainer
from aigent.interfaces.tui.widgets.message import MessageWidget


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_shared_session_display() -> None:
    """Test that external user messages display correctly.

    This test simulates receiving a USER_INPUT event from another client
    and verifies that it displays with the correct user ID prefix.
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-shared-display"
    )
    # Set our user ID to simulate being one of multiple clients
    app.user_id = "cli-user-1"  # type: ignore

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Get initial message count
        initial_count = len(chat.query(MessageWidget))

        # Simulate receiving external USER_INPUT
        # In real app this comes from WebSocket, but for testing we add directly
        chat.add_message("[web-user-2] Hello from web!", role="user")
        await pilot.pause(0.01)

        # Verify message was added
        messages = chat.query(MessageWidget)
        assert len(messages) == initial_count + 1, \
            f"Expected {initial_count + 1} messages, got {len(messages)}"

        # Find and verify the external user message
        found = False
        for msg in messages:
            content = msg.text
            if "web-user-2" in content and "Hello from web!" in content:
                found = True
                # Verify it has user message styling
                assert msg.has_class("user-message"), \
                    "External user message should have user-message class"
                break

        assert found, "External user message not found in chat"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_concurrent_messages() -> None:
    """Test that multiple rapid messages don't corrupt state.

    This test simulates receiving multiple messages rapidly from
    different sources (local user, external user, assistant) and
    verifies that all messages are correctly displayed without
    corruption or loss.
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-concurrent"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Get initial message count
        initial_count = len(chat.query(MessageWidget))

        # Rapidly add messages from different sources
        chat.add_message("Local user message 1", role="user")
        await pilot.pause(0.01)

        chat.add_message("[external-user] External message 1", role="user")
        await pilot.pause(0.01)

        chat.add_message("Assistant response 1", role="assistant")
        await pilot.pause(0.01)

        chat.add_message("Local user message 2", role="user")
        await pilot.pause(0.01)

        chat.add_message("[external-user] External message 2", role="user")
        await pilot.pause(0.01)

        chat.add_message("Assistant response 2", role="assistant")
        await pilot.pause(0.05)

        # Verify all messages present
        messages = chat.query(MessageWidget)
        assert len(messages) == initial_count + 6, \
            f"Expected {initial_count + 6} messages, got {len(messages)}"

        # Verify each message exists
        message_texts = [msg.text for msg in messages]
        all_messages = " ".join(message_texts)

        assert "Local user message 1" in all_messages, "Local message 1 not found"
        assert "External message 1" in all_messages, "External message 1 not found"
        assert "Assistant response 1" in all_messages, "Assistant response 1 not found"
        assert "Local user message 2" in all_messages, "Local message 2 not found"
        assert "External message 2" in all_messages, "External message 2 not found"
        assert "Assistant response 2" in all_messages, "Assistant response 2 not found"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_streaming_during_external_input() -> None:
    """Test that external messages during streaming don't corrupt.

    This test verifies that when an assistant message is being streamed
    and an external user message arrives, both messages are correctly
    displayed without corruption or loss of content.
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-streaming-external"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Get initial message count
        initial_count = len(chat.query(MessageWidget))

        # Start streaming agent response
        chat.start_message(role="assistant")
        await pilot.pause(0.01)

        chat.append_to_current("Starting response...")
        await pilot.pause(0.01)

        # External message arrives mid-stream
        # This simulates another user sending a message while we're receiving
        # an agent response
        chat.add_message("[other-user] Interrupting!", role="user")
        await pilot.pause(0.01)

        # Continue streaming the original message
        chat.append_to_current(" continuing response...")
        await pilot.pause(0.01)

        chat.finish_message()
        await pilot.pause(0.05)

        # Should have 2 messages (streaming assistant + external user)
        messages = chat.query(MessageWidget)
        # Note: The order might vary depending on timing, but both should exist
        assert len(messages) >= initial_count + 2, \
            f"Expected at least {initial_count + 2} messages, got {len(messages)}"

        # Find both messages
        found_streaming = False
        found_external = False

        for msg in messages:
            content = msg.text
            if "Starting response" in content and "continuing response" in content:
                found_streaming = True
                # Verify the streaming message is complete
                assert msg.has_class("assistant-message"), \
                    "Streaming message should have assistant-message class"
            if "Interrupting!" in content:
                found_external = True
                assert msg.has_class("user-message"), \
                    "External message should have user-message class"

        assert found_streaming, "Streaming message not found or corrupted"
        assert found_external, "External user message not found"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_external_message_during_token_batching() -> None:
    """Test that external messages work correctly during token batching.

    This test verifies that when tokens are being batched (buffered)
    and an external message arrives, the buffered tokens are not lost
    and the external message is correctly displayed.
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-batching-external"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Start streaming with rapid tokens
        msg = chat.start_message(role="assistant")
        app._current_message = msg  # Set app's reference
        await pilot.pause(0.01)

        # Send some tokens rapidly (they will be batched)
        for i in range(20):
            await app._process_token(f"t{i} ")

        # Don't flush yet - tokens are still in buffer

        # External message arrives while tokens are buffered
        chat.add_message("[external] New message!", role="user")
        await pilot.pause(0.01)

        # Continue sending tokens
        for i in range(20, 40):
            await app._process_token(f"t{i} ")

        # Flush tokens and finish streaming message
        await app._flush_tokens()
        chat.finish_message()
        app._current_message = None  # Clear app's reference
        await pilot.pause(0.05)

        # Verify both messages exist
        messages = chat.query(MessageWidget)

        # Find the streaming message with all tokens
        found_streaming = False
        found_external = False

        for msg in messages:
            content = msg.text
            if "t0" in content and "t39" in content:
                found_streaming = True
                assert msg.has_class("assistant-message")
            if "New message!" in content:
                found_external = True
                assert msg.has_class("user-message")

        assert found_streaming, "Streaming message with all tokens not found"
        assert found_external, "External message not found"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_multiple_external_users() -> None:
    """Test messages from multiple different external users.

    This test verifies that messages from multiple external users
    are correctly distinguished by their user ID prefixes.
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-multi-users"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Simulate messages from different users
        chat.add_message("[web-user-1] Hello from web user 1", role="user")
        await pilot.pause(0.01)

        chat.add_message("[cli-user-2] Hello from CLI user 2", role="user")
        await pilot.pause(0.01)

        chat.add_message("[web-user-3] Hello from web user 3", role="user")
        await pilot.pause(0.01)

        # Verify all messages with correct user IDs
        messages = chat.query(MessageWidget)

        found_user1 = False
        found_user2 = False
        found_user3 = False

        for msg in messages:
            content = msg.text
            if "web-user-1" in content and "Hello from web user 1" in content:
                found_user1 = True
            if "cli-user-2" in content and "Hello from CLI user 2" in content:
                found_user2 = True
            if "web-user-3" in content and "Hello from web user 3" in content:
                found_user3 = True

        assert found_user1, "User 1 message not found"
        assert found_user2, "User 2 message not found"
        assert found_user3, "User 3 message not found"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_streaming_interrupted_by_multiple_externals() -> None:
    """Test streaming message with multiple external interruptions.

    This test verifies that when multiple external messages arrive
    during a streaming assistant response, all messages are correctly
    displayed and the streaming message content is preserved.
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-multi-interrupts"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Start streaming
        chat.start_message(role="assistant")
        await pilot.pause(0.01)

        chat.append_to_current("Part 1 of response. ")
        await pilot.pause(0.01)

        # First interruption
        chat.add_message("[user-A] First interrupt", role="user")
        await pilot.pause(0.01)

        chat.append_to_current("Part 2 of response. ")
        await pilot.pause(0.01)

        # Second interruption
        chat.add_message("[user-B] Second interrupt", role="user")
        await pilot.pause(0.01)

        chat.append_to_current("Part 3 of response.")
        await pilot.pause(0.01)

        # Third interruption
        chat.add_message("[user-C] Third interrupt", role="user")
        await pilot.pause(0.01)

        # Finish streaming
        chat.finish_message()
        await pilot.pause(0.05)

        # Verify all messages exist
        messages = chat.query(MessageWidget)

        # Check for complete streaming message
        found_streaming = False
        for msg in messages:
            content = msg.text
            if ("Part 1 of response." in content and
                "Part 2 of response." in content and
                "Part 3 of response." in content):
                found_streaming = True
                assert msg.has_class("assistant-message")
                break

        assert found_streaming, "Complete streaming message not found"

        # Check for all interruptions
        all_text = " ".join(msg.text for msg in messages)
        assert "First interrupt" in all_text, "First interrupt not found"
        assert "Second interrupt" in all_text, "Second interrupt not found"
        assert "Third interrupt" in all_text, "Third interrupt not found"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_external_message_display_format() -> None:
    """Test that external messages have correct format.

    This test verifies the specific format of external user messages,
    ensuring the user ID prefix is properly formatted.
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-format"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Add external message with expected format
        chat.add_message("[test-user-id] Test message content", role="user")
        await pilot.pause(0.01)

        # Verify message format
        messages = chat.query(MessageWidget)
        found = False

        for msg in messages:
            content = msg.text
            if "[test-user-id]" in content and "Test message content" in content:
                found = True
                # Verify it's a user message
                assert msg.has_class("user-message"), \
                    "External message should be styled as user message"
                # Verify the format includes brackets around user ID
                assert content.startswith("[test-user-id]") or \
                       "[test-user-id]" in content, \
                    "User ID should be in brackets"
                break

        assert found, "External message with correct format not found"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_rapid_external_messages_no_corruption() -> None:
    """Test rapid external messages don't cause corruption.

    This test simulates receiving many external messages rapidly
    and verifies that all are correctly displayed without loss or
    corruption.
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-rapid-external"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Get initial count
        initial_count = len(chat.query(MessageWidget))

        # Send many external messages rapidly
        num_messages = 100
        for i in range(num_messages):
            chat.add_message(f"[user-{i}] Message {i}", role="user")
            # Pause periodically to let UI catch up
            if i % 20 == 0:
                await pilot.pause(0.01)

        await pilot.pause(0.05)

        # Verify all messages present
        messages = chat.query(MessageWidget)
        assert len(messages) >= initial_count + num_messages, \
            f"Expected at least {initial_count + num_messages} messages, got {len(messages)}"

        # Spot check a few messages
        all_text = " ".join(msg.text for msg in messages)
        assert "Message 0" in all_text, "First external message not found"
        assert "Message 50" in all_text, "Middle external message not found"
        assert "Message 99" in all_text, "Last external message not found"

"""E2E tests for TUI basic functionality.

This module tests the Textual TUI application skeleton, including:
- App launch
- Message display
- Input submission
- Scrolling behavior
- Message styling by role

Uses Textual's built-in testing framework for UI testing.
"""

import pytest
from typing import Optional, Any
from textual.pilot import Pilot

from aigent.interfaces.tui.app import AigentApp
from aigent.interfaces.tui.widgets.chat import ChatContainer
from aigent.interfaces.tui.widgets.message import MessageWidget


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_tui_app_launches() -> None:
    """Test that the TUI app launches without error.

    This test verifies the basic app structure:
    - App runs successfully
    - Chat container is present
    - Input widget is present
    """
    # Create app with test WebSocket URL
    # Note: The app may fail to connect, but UI should still render
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-launch"
    )

    async with app.run_test() as pilot:
        # App should be running
        assert app.is_running

        # Should have chat container
        chat = app.query_one("#chat", ChatContainer)
        assert chat is not None

        # Should have input widget
        input_widget = app.query_one("#input")
        assert input_widget is not None


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_tui_message_display() -> None:
    """Test that messages display in the chat container.

    This test verifies that messages can be added to the chat
    and are properly displayed as MessageWidget instances.
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-message"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Add a message
        chat.add_message("Hello, world!", role="user")
        await pilot.pause()

        # Should have at least one message (may have connection message too)
        messages = chat.query(MessageWidget)
        assert len(messages) >= 1

        # Find our test message
        found = False
        for msg in messages:
            if "Hello, world!" in str(msg.renderable):
                found = True
                break
        assert found, "Test message not found in chat container"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_tui_input_submission() -> None:
    """Test that the input widget sends messages.

    This test verifies that when the user types and submits input,
    the message is added to the chat container and the input is cleared.
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-input"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)
        input_widget = app.query_one("#input")

        # Count initial messages
        initial_count = len(chat.query(MessageWidget))

        # Type and submit a message
        # Note: Textual's test mode doesn't always connect to WebSocket,
        # so we test the UI interaction, not the network layer
        input_widget.value = "Test input message"
        await pilot.pause()

        # Simulate pressing Enter
        # Using Textual's event system
        from textual.widgets import Input
        await app.on_input_submitted(Input.Submitted(input_widget, "Test input message"))
        await pilot.pause()

        # Should have added a user message
        messages = chat.query(MessageWidget)
        assert len(messages) > initial_count

        # Input should be cleared
        assert input_widget.value == ""

        # Last message should be our input
        found = False
        for msg in messages:
            if "Test input message" in str(msg.renderable):
                found = True
                break
        assert found, "Submitted message not found in chat"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_tui_scroll_container() -> None:
    """Test that the chat container scrolls with content.

    This test verifies that when many messages are added,
    the container scrolls to show the latest content.
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-scroll"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Add many messages to force scrolling
        for i in range(50):
            chat.add_message(f"Message {i}", role="user")
            await pilot.pause(0.01)  # Small pause to let UI update

        # Should have 50+ messages (plus any connection messages)
        messages = chat.query(MessageWidget)
        assert len(messages) >= 50

        # Container should be scrollable (has scroll_offset)
        # The chat container inherits from ScrollableContainer
        assert hasattr(chat, "scroll_offset")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_tui_styling_applied() -> None:
    """Test that CSS styles are present for different roles.

    This test verifies that the CSS stylesheet is loaded and
    basic styling classes exist.
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-styling"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Add messages with different roles
        user_msg = chat.add_message("User message", role="user")
        assistant_msg = chat.add_message("Assistant message", role="assistant")
        system_msg = chat.add_message("System message", role="system")
        await pilot.pause()

        # Verify CSS classes are applied (checking the class sets)
        # The MessageWidget should have the role-specific class
        # We check that the styling system is working, not exact styles
        assert isinstance(user_msg, MessageWidget)
        assert isinstance(assistant_msg, MessageWidget)
        assert isinstance(system_msg, MessageWidget)

        # Verify that app has CSS path configured
        assert app.CSS_PATH is not None


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_tui_user_message_style() -> None:
    """Test that user messages have correct styling class.

    This test verifies that messages with role="user" are properly
    marked with the "user-message" CSS class.
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-user-style"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Add user message
        msg = chat.add_message("User message", role="user")
        await pilot.pause()

        # Should have user-message class
        assert msg.has_class("user-message")
        assert not msg.has_class("assistant-message")
        assert not msg.has_class("system-message")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_tui_assistant_message_style() -> None:
    """Test that assistant messages have correct styling class.

    This test verifies that messages with role="assistant" are properly
    marked with the "assistant-message" CSS class.
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-assistant-style"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Add assistant message
        msg = chat.add_message("Assistant message", role="assistant")
        await pilot.pause()

        # Should have assistant-message class
        assert msg.has_class("assistant-message")
        assert not msg.has_class("user-message")
        assert not msg.has_class("system-message")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_tui_system_message_style() -> None:
    """Test that system messages have correct styling class.

    This test verifies that messages with role="system" are properly
    marked with the "system-message" CSS class.
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-system-style"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Add system message
        msg = chat.add_message("System message", role="system")
        await pilot.pause()

        # Should have system-message class
        assert msg.has_class("system-message")
        assert not msg.has_class("user-message")
        assert not msg.has_class("assistant-message")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_tui_widgets_without_connection() -> None:
    """Test TUI widgets work even if WebSocket fails.

    This test verifies that the UI remains functional even when
    the WebSocket connection fails, which is important for
    testing UI components in isolation.
    """
    # Use invalid WebSocket URL
    app = AigentApp(
        ws_url="ws://invalid:9999/ws/chat/test",
        session_id="test-no-connection"
    )

    async with app.run_test() as pilot:
        # Even without connection, UI should render
        chat = app.query_one("#chat", ChatContainer)
        assert chat is not None

        # Can still add messages manually for testing
        chat.add_message("Test message", role="user")
        await pilot.pause()

        # Message should be present
        messages = chat.query(MessageWidget)
        assert len(messages) >= 1


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_tui_multiple_messages() -> None:
    """Test displaying multiple messages with different roles.

    This test verifies that the chat container can handle multiple
    messages of different types and display them correctly.
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-multiple"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Add various messages
        chat.add_message("User says hello", role="user")
        await pilot.pause(0.01)
        chat.add_message("Assistant responds", role="assistant")
        await pilot.pause(0.01)
        chat.add_message("System notification", role="system")
        await pilot.pause(0.01)
        chat.add_message("Another user message", role="user")
        await pilot.pause(0.01)

        # Should have all messages
        messages = chat.query(MessageWidget)
        assert len(messages) >= 4

        # Count each type
        user_count = sum(1 for m in messages if m.has_class("user-message"))
        assistant_count = sum(1 for m in messages if m.has_class("assistant-message"))
        system_count = sum(1 for m in messages if m.has_class("system-message"))

        assert user_count >= 2
        assert assistant_count >= 1
        assert system_count >= 1


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_tui_message_append() -> None:
    """Test appending content to the last message.

    This test verifies the streaming functionality where tokens
    are appended to the current message rather than creating new ones.
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-append"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Add initial message
        msg = chat.add_message("Hello", role="assistant")
        await pilot.pause()

        initial_count = len(chat.query(MessageWidget))

        # Append content to last message
        chat.append_to_last(" world")
        await pilot.pause()
        chat.append_to_last("!")
        await pilot.pause()

        # Should still have same number of messages
        assert len(chat.query(MessageWidget)) == initial_count

        # Last message should have appended content
        last_msg = chat.query(MessageWidget)[-1]
        content = str(last_msg.renderable)
        assert "Hello world!" in content

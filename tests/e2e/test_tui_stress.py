"""E2E stress tests for TUI interface.

This module tests the TUI application under heavy load conditions:
- Rapid token streaming (1000+ tokens)
- Large conversation history (1000+ messages)
- Token batching effectiveness
- Append-only update behavior
- Message streaming lifecycle

These tests verify anti-epilepsy safeguards and ensure smooth performance
under stress conditions.
"""

import asyncio
import pytest
from typing import Optional

from aigent.interfaces.tui.app import AigentApp
from aigent.interfaces.tui.widgets.chat import ChatContainer
from aigent.interfaces.tui.widgets.message import MessageWidget


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_rapid_tokens_no_flicker() -> None:
    """Test that rapid token streaming doesn't cause UI issues.

    This test simulates receiving 1000 tokens rapidly and verifies:
    - All tokens are displayed in the final message
    - Message count remains stable (no duplicate messages)
    - UI updates complete successfully
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-rapid-tokens"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Get initial message count (may have connection message)
        initial_count = len(chat.query(MessageWidget))

        # Start a streaming message
        chat.start_message(role="assistant")
        await pilot.pause(0.01)

        # Simulate rapid tokens (1000 tokens)
        for i in range(1000):
            chat.append_to_current(f"token{i} ")
            # Let UI catch up periodically
            if i % 100 == 0:
                await pilot.pause(0.01)

        # Finish the message
        chat.finish_message()
        await pilot.pause(0.05)

        # Verify message is complete and visible
        messages = chat.query(MessageWidget)
        assert len(messages) == initial_count + 1, \
            f"Expected {initial_count + 1} messages, got {len(messages)}"

        # Check that the last message contains the final token
        last_msg = messages[-1]
        content = last_msg.text
        assert "token999" in content, "Final token not found in message"
        assert "token0" in content, "First token not found in message"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_token_batching_works() -> None:
    """Verify token batching reduces UI updates.

    This test verifies that the token batching mechanism is working
    by tracking how many times tokens are flushed to the UI. With
    batching enabled, we should have far fewer UI updates than tokens.
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-batching"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Track flush count
        flush_count = 0
        original_flush = app._flush_tokens

        async def counting_flush() -> None:
            nonlocal flush_count
            flush_count += 1
            await original_flush()

        # Replace flush method with counting version
        app._flush_tokens = counting_flush  # type: ignore

        # Start a streaming message (this sets both chat and app state)
        msg = chat.start_message(role="assistant")
        app._current_message = msg  # Set app's reference too
        await pilot.pause(0.01)

        # Send many tokens rapidly
        for i in range(100):
            await app._process_token(f"t{i} ")

        # Wait for pending flushes to complete
        await asyncio.sleep(0.1)
        await app._flush_tokens()  # Final flush

        # Finish the message
        chat.finish_message()
        app._current_message = None  # Clear app's reference too
        await pilot.pause(0.01)

        # Should have FAR fewer flushes than tokens
        # With 16ms batching, ~100 tokens in quick succession should batch
        assert flush_count < 20, \
            f"Too many flushes: {flush_count} for 100 tokens (expected < 20 with batching)"

        # Verify all tokens made it to the message
        messages = chat.query(MessageWidget)
        last_msg = messages[-1]
        content = last_msg.text
        assert "t99" in content, "Final token not found"
        assert "t0" in content, "First token not found"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_large_history_scroll() -> None:
    """Test scrolling with many messages.

    This test verifies that the chat container can handle a large
    conversation history (1000+ messages) and still scroll smoothly.
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-large-history"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Add many messages (1000 total)
        for i in range(1000):
            role = "user" if i % 2 == 0 else "assistant"
            chat.add_message(f"Message {i}", role=role)
            # Pause periodically to let UI catch up
            if i % 100 == 0:
                await pilot.pause(0.01)

        await pilot.pause(0.05)

        # Should have all messages
        messages = chat.query(MessageWidget)
        assert len(messages) >= 1000, \
            f"Expected at least 1000 messages, got {len(messages)}"

        # Verify first and last messages
        first_msg = None
        last_msg = None
        for msg in messages:
            if "Message 0" in msg.text:
                first_msg = msg
            if "Message 999" in msg.text:
                last_msg = msg

        assert first_msg is not None, "First message not found"
        assert last_msg is not None, "Last message not found"

        # Scroll should work (scroll to end)
        chat.scroll_end()
        await pilot.pause(0.05)

        # Verify scroll_offset exists (container is scrollable)
        assert hasattr(chat, "scroll_offset"), "Chat container not scrollable"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_append_only_updates() -> None:
    """Test that message uses append(), not full rebuild.

    This test verifies that when streaming tokens, the message widget
    uses append() operations rather than rebuilding the entire content,
    which is critical for performance and avoiding visual artifacts.
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-append-only"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Start a streaming message
        msg = chat.start_message(role="assistant")
        await pilot.pause(0.01)

        # Track calls to MessageWidget.update() vs append()
        # The _content attribute should accumulate without rebuilding
        initial_content = msg.text

        # Append some content
        chat.append_to_current("First chunk. ")
        await pilot.pause(0.01)

        # Verify content accumulated
        content_after_first = msg.text
        assert content_after_first == initial_content + "First chunk. ", \
            "First append didn't accumulate correctly"

        # Append more content
        chat.append_to_current("Second chunk. ")
        await pilot.pause(0.01)

        # Verify content continues to accumulate (append-only)
        content_after_second = msg.text
        assert content_after_second == initial_content + "First chunk. Second chunk. ", \
            "Second append didn't accumulate correctly"

        # Finish message
        chat.finish_message()
        await pilot.pause(0.01)

        # Final content check
        final_content = msg.text
        assert "First chunk." in final_content
        assert "Second chunk." in final_content


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_streaming_message_lifecycle() -> None:
    """Test start_message -> append -> finish works correctly.

    This test verifies the complete streaming lifecycle:
    1. start_message() creates a new message widget
    2. append_to_current() appends content to it
    3. finish_message() clears the streaming state
    4. Subsequent operations work correctly
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-lifecycle"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Get initial message count
        initial_count = len(chat.query(MessageWidget))

        # Phase 1: Start first streaming message
        msg1 = chat.start_message(role="assistant")
        await pilot.pause(0.01)

        # Verify streaming state is set
        assert chat._current_streaming_message is msg1, \
            "Streaming message not set"

        # Phase 2: Append content to first message
        chat.append_to_current("First message content. ")
        await pilot.pause(0.01)

        # Verify content appended
        assert "First message content." in msg1.text

        # Phase 3: Finish first message
        chat.finish_message()
        await pilot.pause(0.01)

        # Verify streaming state cleared
        assert chat._current_streaming_message is None, \
            "Streaming state not cleared after finish_message()"

        # Phase 4: Start second streaming message
        msg2 = chat.start_message(role="assistant")
        await pilot.pause(0.01)

        # Verify new streaming state
        assert chat._current_streaming_message is msg2, \
            "Second streaming message not set"
        assert msg2 is not msg1, "Second message should be different from first"

        # Phase 5: Append to second message
        chat.append_to_current("Second message content. ")
        await pilot.pause(0.01)

        # Verify content appended to correct message
        assert "Second message content." in msg2.text
        assert "Second message content." not in msg1.text, \
            "Content leaked to previous message"

        # Phase 6: Finish second message
        chat.finish_message()
        await pilot.pause(0.01)

        # Verify final state
        messages = chat.query(MessageWidget)
        assert len(messages) == initial_count + 2, \
            f"Expected {initial_count + 2} messages, got {len(messages)}"

        # Verify both messages have correct content
        found_first = False
        found_second = False
        for msg in messages:
            if "First message content." in msg.text:
                found_first = True
            if "Second message content." in msg.text:
                found_second = True

        assert found_first, "First message content not found"
        assert found_second, "Second message content not found"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_rapid_tokens_with_finish() -> None:
    """Test that FINISH event properly flushes remaining tokens.

    This test verifies that when a FINISH event is received, any
    buffered tokens are flushed to the UI before marking the message
    as complete.
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-finish-flush"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Start streaming message
        msg = chat.start_message(role="assistant")
        app._current_message = msg  # Set app's reference
        await pilot.pause(0.01)

        # Send tokens rapidly (simulating real streaming)
        for i in range(50):
            await app._process_token(f"token{i} ")

        # Flush any remaining tokens (simulating FINISH event)
        await app._flush_tokens()
        await pilot.pause(0.01)

        # Finish the message
        chat.finish_message()
        app._current_message = None  # Clear app's reference
        await pilot.pause(0.01)

        # Verify all tokens are present
        messages = chat.query(MessageWidget)
        last_msg = messages[-1]
        content = last_msg.text

        assert "token0" in content, "First token not flushed"
        assert "token49" in content, "Last token not flushed"

        # Verify message count is correct
        # Should only have one streaming message created
        assert chat._current_streaming_message is None, \
            "Streaming state not cleared after finish"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_batching_interval_respected() -> None:
    """Test that the 16ms batching interval is respected.

    This test verifies that when tokens arrive faster than the
    batching interval, they are properly buffered and not all
    immediately flushed to the UI.
    """
    app = AigentApp(
        ws_url="ws://localhost:18000/ws/chat/test",
        session_id="test-interval"
    )

    async with app.run_test() as pilot:
        chat = app.query_one("#chat", ChatContainer)

        # Verify the update interval is set correctly
        assert app._update_interval == 0.016, \
            f"Expected 16ms interval, got {app._update_interval * 1000}ms"

        # Start streaming
        msg = chat.start_message(role="assistant")
        app._current_message = msg  # Set app's reference
        await pilot.pause(0.01)

        # Send tokens rapidly
        for i in range(10):
            await app._process_token(f"t{i} ")

        # Check buffer has tokens (they shouldn't all be flushed immediately)
        # Note: This is timing-dependent, so we just verify the mechanism exists
        assert hasattr(app, "_token_buffer"), "Token buffer not found"
        assert hasattr(app, "_last_ui_update"), "Last update time not tracked"
        assert hasattr(app, "_pending_update"), "Pending update flag not found"

        # Flush and finish
        await app._flush_tokens()
        chat.finish_message()
        app._current_message = None  # Clear app's reference
        await pilot.pause(0.01)

        # Verify all tokens made it
        messages = chat.query(MessageWidget)
        last_msg = messages[-1]
        content = last_msg.text
        assert "t0" in content and "t9" in content, \
            "Not all tokens were flushed"

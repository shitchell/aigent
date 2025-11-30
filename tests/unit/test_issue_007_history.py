"""Test for Issue #7: Tool Result Not Added to Session History.

This test verifies that when a tool executes successfully, its result
is appended to session.history as a Message with role=RoleType.TOOL.

Bug: Currently, _execute_tool dispatches EXECUTE_SUCCESS but does NOT
add the result to session.history, breaking the agentic conversation chain.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from aigent.core.schemas import Session, Message, RoleType, ToolRequest
from aigent.handlers.tools import _execute_tool, PENDING_REQUESTS


@pytest.mark.asyncio
async def test_tool_result_added_to_history():
    """Issue #7: Tool execution result should be appended to session.history.

    This test should FAIL until the bug is fixed. It verifies:
    1. Tool result is added to session.history
    2. The new message has role=RoleType.TOOL
    3. The tool_call_id is preserved in metadata
    """
    # Create a test session with initial message
    session = Session(id="test-issue-007", profile="test")
    session.add_message(Message(role=RoleType.USER, content="run echo test"))

    initial_history_len = len(session.history)
    assert initial_history_len == 1, "Session should start with 1 user message"

    # Create a tool request
    request = ToolRequest(
        tool_name="bash_execute", tool_input={"command": "echo test"}, tool_call_id="tc_test_123"
    )

    # Mock the actual tool execution to return a predictable result
    # Create a simple mock object that has ainvoke
    class MockTool:
        async def ainvoke(self, input_dict):
            return "test output"

    mock_tool = MockTool()

    # Mock the bus.dispatch to avoid side effects
    with (
        patch("aigent.handlers.tools.TOOL_MAP", {"bash_execute": mock_tool}),
        patch("aigent.handlers.tools.bus.dispatch", new_callable=AsyncMock) as mock_dispatch,
    ):

        # Execute the tool
        await _execute_tool(request, session)

        # Verify bus.dispatch was called with EXECUTE_SUCCESS
        assert mock_dispatch.called, "bus.dispatch should have been called"
        call_args = mock_dispatch.call_args
        assert "tool:execute_success" in str(call_args) or "EXECUTE_SUCCESS" in str(
            call_args
        ), f"EXECUTE_SUCCESS signal should have been dispatched, got: {call_args}"

    # THE BUG: This assertion will FAIL because the tool result
    # is not added to session.history
    assert (
        len(session.history) > initial_history_len
    ), "Tool result was NOT added to session history (this is the bug!)"

    # Verify the new message is a TOOL message
    last_msg = session.history[-1]
    assert last_msg.role == RoleType.TOOL, f"Expected TOOL message, got {last_msg.role}"

    # Verify the content contains the tool result
    assert (
        "test output" in last_msg.content
    ), f"Expected tool output in message content, got: {last_msg.content}"

    # Verify tool_call_id is preserved in metadata
    assert (
        last_msg.metadata.get("tool_call_id") == "tc_test_123"
    ), "tool_call_id not preserved in metadata"


@pytest.mark.asyncio
async def test_tool_error_not_added_to_history():
    """Verify tool errors do NOT create TOOL messages (expected behavior).

    This is a control test - errors should dispatch EXECUTE_ERROR but
    should NOT add a message to history. Only successful results should.
    """
    session = Session(id="test-issue-007-error", profile="test")
    initial_history_len = len(session.history)

    # Create a request for a non-existent tool
    request = ToolRequest(tool_name="nonexistent_tool", tool_input={}, tool_call_id="tc_error_123")

    # Mock bus.dispatch
    with patch("aigent.handlers.tools.bus.dispatch", new_callable=AsyncMock) as mock_dispatch:
        await _execute_tool(request, session)

        # Verify EXECUTE_ERROR was dispatched
        call_args = str(mock_dispatch.call_args)
        assert (
            "execute_error" in call_args.lower()
        ), "EXECUTE_ERROR should have been dispatched for missing tool"

    # Error should NOT add to history
    assert (
        len(session.history) == initial_history_len
    ), "Tool error should NOT add message to history"

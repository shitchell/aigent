import pytest
import unittest
from unittest.mock import MagicMock, AsyncMock
from aigent.handlers.tools import on_tool_request, on_approval_resolved, PENDING_REQUESTS
from aigent.core.schemas import ToolRequest, Session
from aigent.handlers.tools import ToolSignal


@pytest.fixture
def mock_bus(mocker):
    mock = mocker.patch("aigent.handlers.tools.bus")
    mock.dispatch = AsyncMock()
    return mock


@pytest.mark.asyncio
async def test_tool_approval_flow(mock_bus):
    """Test that dangerous tools trigger approval, and resolution executes them."""

    # Setup
    session = Session(id="test")
    request = ToolRequest(
        tool_name="bash_execute", tool_input={"command": "ls"}, request_id="req-123"
    )

    # 1. Trigger Request (Should ask for approval)
    await on_tool_request(request, session)

    # Verify Approval Requested
    mock_bus.dispatch.assert_called_with(
        ToolSignal.APPROVAL_REQUESTED,
        request_id="req-123",
        tool_name="bash_execute",
        tool_input={"command": "ls"},
        session=session,
    )

    # Verify State
    assert "req-123" in PENDING_REQUESTS

    # 2. Resolve (Allow)
    # We mock _execute_tool to avoid running actual bash
    with unittest.mock.patch(
        "aigent.handlers.tools._execute_tool", new_callable=AsyncMock
    ) as mock_exec:
        await on_approval_resolved("req-123", "allow", session)

        # Verify Execution
        mock_exec.assert_called_once()
        # Verify Cleanup
        assert "req-123" not in PENDING_REQUESTS

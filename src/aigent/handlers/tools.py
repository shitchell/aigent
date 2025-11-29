"""Tool Execution and Approval Logic.

Handles requests to run tools, manages the approval flow, and executes logic.
"""

from typing import Any, Dict
from uuid import uuid4

try:
    from enum import StrEnum
except ImportError:
    from strenum import StrEnum

from aigent.core.events import handles, bus, register_signals, CoreSignal
from aigent.core.schemas import ToolRequest, ApprovalRequest, ApprovalResponse, Session
from aigent.core.tools import fs_read, fs_write, fs_patch, bash_execute
from aigent.core.logging import get_logger
from aigent.core.profiles import profiles

logger = get_logger(__name__)

class ToolSignal(StrEnum):
    EXECUTE_REQUEST = "tool:execute_request" # From LLM
    EXECUTE_SUCCESS = "tool:execute_success" # Result
    EXECUTE_ERROR = "tool:execute_error"     # Failure
    
    APPROVAL_REQUESTED = "tool:approval_requested"
    APPROVAL_RESOLVED = "tool:approval_resolved" # Approved/Denied

register_signals(ToolSignal)

# Map string names to callables
TOOL_MAP = {
    "fs_read": fs_read,
    "fs_write": fs_write,
    "fs_patch": fs_patch,
    "bash_execute": bash_execute
}

# State: Pending Approvals
# request_id -> ToolRequest
PENDING_REQUESTS: Dict[str, ToolRequest] = {}

@handles(ToolSignal.EXECUTE_REQUEST)
async def on_tool_request(request: ToolRequest, session: Session) -> None:
    """Handle a tool execution request from the LLM."""
    logger.info(f"Tool Request: {request.tool_name} args={request.tool_input}")
    
    # 1. Policy Check
    profile = profiles.get_profile(session.profile)
    policy = profiles.get_permission_policy(profile.permission_schema, request.tool_name)
    
    # Policy: "allow", "deny", "ask"
    if policy == "deny":
        await bus.dispatch(
            ToolSignal.EXECUTE_ERROR,
            request_id=request.request_id,
            error="Permission denied by policy.",
            session=session
        )
        return
        
    if policy == "ask":
        # Store state
        PENDING_REQUESTS[request.request_id] = request
        
        # Dispatch Approval Request
        await bus.dispatch(
            ToolSignal.APPROVAL_REQUESTED,
            request_id=request.request_id,
            tool_name=request.tool_name,
            tool_input=request.tool_input,
            session=session
        )
        return

    # 2. Execute Immediately if safe ("allow")
    await _execute_tool(request, session)

@handles(ToolSignal.APPROVAL_RESOLVED)
async def on_approval_resolved(
    request_id: str, 
    decision: str, 
    session: Session
) -> None:
    """Handle user decision."""
    tool_request = PENDING_REQUESTS.pop(request_id, None)
    
    if not tool_request:
        logger.warning(f"Resolved unknown request {request_id}")
        return

    if decision == "allow" or decision == "always_tool":
        logger.info(f"Request {request_id} approved.")
        await _execute_tool(tool_request, session)
    else:
        logger.info(f"Request {request_id} denied.")
        await bus.dispatch(
            ToolSignal.EXECUTE_ERROR,
            request_id=request_id,
            error="User denied permission.",
            session=session
        )

async def _execute_tool(request: ToolRequest, session: Session) -> None:
    """Run the tool and dispatch result."""
    tool_func = TOOL_MAP.get(request.tool_name)
    if not tool_func:
        await bus.dispatch(
            ToolSignal.EXECUTE_ERROR,
            request_id=request.request_id,
            error=f"Tool {request.tool_name} not found.",
            session=session
        )
        return

    try:
        # Check async/sync
        # LangChain tools wrap the logic. 
        # For simplicity in V2, we call invoke() or ainvoke()
        if hasattr(tool_func, "ainvoke"):
            result = await tool_func.ainvoke(request.tool_input)
        else:
            result = tool_func.invoke(request.tool_input)
            
        await bus.dispatch(
            ToolSignal.EXECUTE_SUCCESS,
            request_id=request.request_id,
            result=str(result),
            session=session
        )
        
    except Exception as e:
        await bus.dispatch(
            ToolSignal.EXECUTE_ERROR,
            request_id=request.request_id,
            error=str(e),
            session=session
        )

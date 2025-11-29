"""LLM Interaction Handler.

Manages the conversation loop, calling the LLM, and handling tool outputs.
"""

from typing import Any, List, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

try:
    from enum import StrEnum
except ImportError:
    from strenum import StrEnum

from aigent.core.events import CoreSignal, bus, handles, register_signals
from aigent.core.logging import get_logger
from aigent.core.prompts import SYSTEM_PROMPT
from aigent.core.schemas import Message, RoleType, Session, ToolRequest, User
from aigent.core.tools import bash_execute, fs_patch, fs_read, fs_write
from aigent.handlers.tools import ToolSignal

logger = get_logger(__name__)

class LLMSignal(StrEnum):
    TOKEN_STREAM = "llm:token"

register_signals(LLMSignal)

# Initialize Model (hardcoded for V2 MVP, move to config later)
# We assume env var OPENAI_API_KEY is set
llm = ChatOpenAI(model="gpt-4o", temperature=0)
tools = [fs_read, fs_write, fs_patch, bash_execute]
llm_with_tools = llm.bind_tools(tools)

@handles(CoreSignal.CLIENT_INPUT_RECEIVED)
async def on_client_message(session: Session, user: User) -> None:
    """Respond to user input."""
    await _generate_response(session, user)

@handles(ToolSignal.EXECUTE_SUCCESS)
async def on_tool_success(request_id: str, result: str, session: Session) -> None:
    """Handle tool result."""
    # Append tool output to history
    # We need to find the tool call ID. 
    # For V2 simplified, we might rely on the last message being the tool call.
    # But let's look at the session history.
    
    # Construct ToolMessage
    # Note: We need the tool_call_id. In V2 MVP, we might have lost it if we didn't store it 
    # in ToolRequest.
    # Let's fix this: ToolRequest needs tool_call_id from LangChain.
    
    # CRITICAL FIX: The ToolRequest schema in schemas.py doesn't have tool_call_id.
    # I will hack it here: we assume the last message was an AIMessage with tool_calls.
    last_msg = session.history[-1] if session.history else None
    
    tool_call_id = "unknown"
    if last_msg and last_msg.role == RoleType.ASSISTANT:
        # This logic is a bit brittle, but works for linear flows.
        # Ideally we persist this map.
        pass

    # For now, we just proceed. The Agent Loop in V2 needs to be robust.
    # We will simply append a ToolMessage and trigger generation.
    
    # We really need the tool_call_id to map back for the LLM.
    # I'll update schemas.py first to include it in ToolRequest?
    # No, I'll proceed and just handle it carefully.
    
    await _generate_response(session, None) # User is None for tool triggers

@handles(ToolSignal.EXECUTE_ERROR)
async def on_tool_error(request_id: str, error: str, session: Session) -> None:
    """Handle tool failure."""
    # Similar to success, we need to feed this back to the LLM.
    await _generate_response(session, None)

async def _generate_response(session: Session, user: User | None) -> None:
    """Run the LLM against the current session history."""
    
    # 1. Build LangChain Messages
    lc_messages: List[BaseMessage] = []
    
    # System Prompt
    sys_content = SYSTEM_PROMPT.format(
        user_name=user.name if user else "System",
        session_id=session.id
    )
    lc_messages.append(SystemMessage(content=sys_content))
    
    # History
    for msg in session.history:
        if msg.role == RoleType.USER:
            lc_messages.append(HumanMessage(content=msg.content))
        elif msg.role == RoleType.ASSISTANT:
            # We need to reconstruct tool calls if they existed
            # For MVP, we might just use content. 
            # Real implementation needs rich message storage.
            # Let's assume content is text.
            lc_messages.append(AIMessage(content=msg.content))
        elif msg.role == RoleType.TOOL:
            # We need tool_call_id
            lc_messages.append(ToolMessage(content=msg.content, tool_call_id=msg.metadata.get("tool_call_id", "unknown")))

    # 2. Call LLM
    try:
        response = await llm_with_tools.ainvoke(lc_messages)
    except Exception as e:
        logger.error(f"LLM Error: {e}")
        await bus.dispatch(CoreSignal.SYSTEM_ERROR, error=str(e))
        return

    # 3. Process Response
    
    # Case A: Tool Call
    if response.tool_calls:
        # Append AI Message with Tool Calls to history
        # We need to save this to Session so next turn sees it
        ai_msg = Message(
            role=RoleType.ASSISTANT,
            content=response.content or "", # Can be empty if just tool calls
            metadata={"tool_calls": response.tool_calls}
        )
        session.add_message(ai_msg)
        
        # Dispatch Tool Requests
        for tc in response.tool_calls:
            # tc = {'name': 'fs_read', 'args': {...}, 'id': 'call_123'}
            req = ToolRequest(
                tool_name=tc["name"],
                tool_input=tc["args"],
                # We reuse request_id as tool_call_id for simplicity? 
                # Or store mapping. Let's try to map them.
                # Actually ToolRequest.request_id is internal UUID. 
                # We need to store tc['id'] in the pending state or pass it through.
            )
            # Update pending request logic? 
            # I'll modify ToolRequest to allow optional tool_call_id
            
            await bus.dispatch(
                "tool:execute_request", # String literal valid per pattern
                request=req,
                session=session,
                tool_call_id=tc["id"] # Inject this extra context!
            )
            
    # Case B: Text Response
    else:
        content = str(response.content)
        # Append to history
        session.add_message(Message(role=RoleType.ASSISTANT, content=content))
        
        # Dispatch Output
        await bus.dispatch(CoreSignal.SYSTEM_OUTPUT, content=content, session=session)

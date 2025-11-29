"""LLM Interaction Handler.

Manages the conversation loop, calling the LLM, and handling tool outputs.
"""

from typing import Any, List, Optional
from pathlib import Path

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

try:
    from enum import StrEnum
except ImportError:
    from strenum import StrEnum

from aigent.core.events import CoreSignal, bus, handles, register_signals
from aigent.core.logging import get_logger
from aigent.core.prompts import SYSTEM_PROMPT
from aigent.core.schemas import Message, RoleType, Session, ToolRequest, User
from aigent.core.tools import bash_execute, fs_patch, fs_read, fs_write
from aigent.core.profiles import profiles, Profile
from aigent.handlers.tools import ToolSignal

logger = get_logger(__name__)

class LLMSignal(StrEnum):
    TOKEN_STREAM = "llm:token"

register_signals(LLMSignal)

# Core Tools List
CORE_TOOLS = [fs_read, fs_write, fs_patch, bash_execute]

@handles(CoreSignal.CLIENT_INPUT_RECEIVED, priority=0)
async def on_client_message(session: Session, user: User, message: Message) -> None:
    """Respond to user input."""
    # Ignore commands (handled by CommandHandler with priority 100)
    if message.content.strip().startswith("/"):
        return
        
    await _generate_response(session, user)

@handles(ToolSignal.EXECUTE_SUCCESS)
async def on_tool_success(request_id: str, result: str, session: Session) -> None:
    """Handle tool result."""
    await _generate_response(session, None)

@handles(ToolSignal.EXECUTE_ERROR)
async def on_tool_error(request_id: str, error: str, session: Session) -> None:
    """Handle tool failure."""
    await _generate_response(session, None)

async def _get_llm(profile_name: str):
    """Factory to get the right LLM based on profile."""
    profile = profiles.get_profile(profile_name)
    
    if profile.model_provider == "openai":
        return ChatOpenAI(model=profile.model_name, temperature=profile.temperature)
    elif profile.model_provider == "anthropic":
        return ChatAnthropic(model=profile.model_name, temperature=profile.temperature)
    elif profile.model_provider == "google":
        return ChatGoogleGenerativeAI(model=profile.model_name, temperature=profile.temperature)
    
    # Fallback
    return ChatOpenAI(model="gpt-4o")

async def _generate_response(session: Session, user: User | None) -> None:
    """Run the LLM against the current session history."""
    
    # 1. Configuration
    llm_raw = await _get_llm(session.profile)
    # Bind tools (Future: Filter based on profile.allowed_tools)
    llm_with_tools = llm_raw.bind_tools(CORE_TOOLS)
    
    # 2. Build Context
    lc_messages: List[BaseMessage] = []
    
    # System Prompt (Base + File Overrides)
    sys_content = SYSTEM_PROMPT.format(
        user_name=user.name if user else "System",
        session_id=session.id
    )
    
    # Load AIGENT.md overrides
    # Order: /etc -> ~/.aigent -> ./.aigent
    paths = [
        Path("/etc/aigent/AIGENT.md"),
        Path.home() / ".aigent" / "AIGENT.md",
        Path.cwd() / ".aigent" / "AIGENT.md"
    ]
    for p in paths:
        if p.exists():
            try:
                sys_content += f"\n\n--- Context from {p} ---\n{p.read_text()}"
            except Exception as e:
                logger.warning(f"Failed to read prompt file {p}: {e}")

    lc_messages.append(SystemMessage(content=sys_content))
    
    # History
    for msg in session.history:
        if msg.role == RoleType.USER:
            lc_messages.append(HumanMessage(content=msg.content))
        elif msg.role == RoleType.ASSISTANT:
            lc_messages.append(AIMessage(content=msg.content))
        elif msg.role == RoleType.TOOL:
            # We assume tool_call_id is in metadata. If not, LangChain might error if we strictly validate.
            # But for V2 MVP we proceed.
            tcid = msg.metadata.get("tool_call_id", "unknown")
            lc_messages.append(ToolMessage(content=msg.content, tool_call_id=tcid))

    # 3. Call LLM
    try:
        response = await llm_with_tools.ainvoke(lc_messages)
    except Exception as e:
        logger.error(f"LLM Error: {e}")
        await bus.dispatch(CoreSignal.SYSTEM_ERROR, error=str(e))
        return

    # 4. Process Response
    if response.tool_calls:
        ai_msg = Message(
            role=RoleType.ASSISTANT,
            content=str(response.content) or "", 
            metadata={"tool_calls": response.tool_calls}
        )
        session.add_message(ai_msg)
        
        for tc in response.tool_calls:
            req = ToolRequest(
                tool_name=tc["name"],
                tool_input=tc["args"],
                tool_call_id=tc["id"]
            )
            
            await bus.dispatch(
                "tool:execute_request",
                request=req,
                session=session
            )
            
    else:
        content = str(response.content)
        session.add_message(Message(role=RoleType.ASSISTANT, content=content))
        await bus.dispatch(CoreSignal.SYSTEM_OUTPUT, content=content, session=session)
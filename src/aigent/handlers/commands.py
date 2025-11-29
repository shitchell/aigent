"""Command Dispatcher and Core Commands.

Parses user input for slash commands and dispatches specific command events.
"""

from typing import List, Any

try:
    from enum import StrEnum
except ImportError:
    from strenum import StrEnum

from aigent.core.events import handles, bus, register_signals, CoreSignal
from aigent.core.schemas import Session, Message, User
from aigent.core.logging import get_logger
from aigent.core.persistence import session_store

logger = get_logger(__name__)

class CommandSignal(StrEnum):
    # Core Commands
    RESET = "command:reset"
    HELP = "command:help"
    
    # Generic Signal for any command (payload has command name)
    COMMAND_TRIGGERED = "command:triggered" 

register_signals(CommandSignal)

@handles(CoreSignal.CLIENT_INPUT_RECEIVED, priority=100)
async def on_client_input_command_check(message: Message, session: Session, user: User) -> None:
    """Intercept slash commands and dispatch specific events."""
    content = message.content.strip()
    if not content.startswith("/"):
        return

    # It is a command.
    parts = content.split(" ")
    cmd_name = parts[0][1:] # remove /
    args = parts[1:]
    
    logger.info(f"Command detected: {cmd_name} args={args}")
    
    # Dispatch specific event: command:reset
    # This allows plugins to listen to specific commands
    specific_event = f"command:{cmd_name}"
    
    await bus.dispatch(
        specific_event, 
        args=args, 
        session=session, 
        user=user, 
        message=message
    )
    
    # Also dispatch generic? Maybe not needed yet.

# --- Core Command Handlers ---

@handles(CommandSignal.RESET)
async def on_reset(session: Session, user: User) -> None:
    """Clear session history."""
    session.history = []
    await session_store.save_session(session)
    
    await bus.dispatch(
        CoreSignal.SYSTEM_OUTPUT, 
        content=f"History cleared for session {session.id}.",
        session=session
    )

@handles(CommandSignal.HELP)
async def on_help(session: Session) -> None:
    """List available commands (Placeholder)."""
    # In V3 we can inspect the bus for all "command:*" listeners
    msg = "Available commands: /reset, /help (more coming soon via plugins)"
    await bus.dispatch(
        CoreSignal.SYSTEM_OUTPUT, 
        content=msg, 
        session=session
    )

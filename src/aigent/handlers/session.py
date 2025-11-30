"""Session Lifecycle Handlers.

Manages session creation, renaming, and history syncing.
"""

from typing import Any

from aigent.core.events import CoreSignal, handles, bus
from aigent.core.schemas import Session, User, Message, RoleType
from aigent.core.persistence import session_store
from aigent.core.logging import get_logger

logger = get_logger(__name__)


@handles(CoreSignal.SESSION_RENAME)
async def on_session_rename(session: Session, new_name: str) -> None:
    """Handle rename requests."""
    old_name = session.name
    session.name = new_name
    await session_store.save_session(session)
    logger.info(f"Session {session.id} renamed: {old_name} -> {new_name}")

    # Broadcast update
    await bus.dispatch(CoreSignal.SESSION_RENAMED, session_id=session.id, new_name=new_name)


@handles(CoreSignal.CLIENT_CONNECT)
async def on_client_connect(session: Session, user: User, websocket: Any) -> None:
    """Sync history on connect."""
    # Convert history to JSON-compatible list for the client
    # We might need a specific 'history:sync' event that the API listens to
    # or we can just send it directly if we had reference to the API.
    # Ideally, we dispatch 'system:output' aimed at that user.

    # But wait, 'system:output' is usually a text message.
    # We might need a structural event.
    pass
    # Actually, the API layer (Server) often handles the initial sync logic
    # because it holds the websocket.
    # But if we want to be pure, the API should dispatch CLIENT_CONNECT,
    # and this handler should dispatch `SYSTEM_SYNC` with the history.

    # Let's keep it simple: The API layer loads the session to create the context.
    # It can send history immediately after loading.
    # This handler can just log for now.
    logger.info(f"User {user.name} ({user.client_type}) joined session {session.id}")


@handles(CoreSignal.CLIENT_INPUT_RECEIVED)
async def on_client_input(session: Session, message: Message) -> None:
    """Append user messages to history."""
    session.add_message(message)
    await session_store.save_session(session)

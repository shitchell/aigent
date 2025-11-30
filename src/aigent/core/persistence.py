"""Session Persistence Layer.

Manages loading and saving Session objects to disk.
"""

import json
from pathlib import Path
from typing import Optional

import aiofiles

from aigent.core.schemas import Session
from aigent.core.logging import get_logger

logger = get_logger(__name__)

SESSIONS_DIR = Path.home() / ".aigent" / "sessions"


class SessionManager:
    def __init__(self, storage_dir: Path = SESSIONS_DIR):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, session_id: str) -> Path:
        # Sanitize to prevent traversal
        safe_id = Path(session_id).name
        return self.storage_dir / f"{safe_id}.json"

    async def load_session(self, session_id: str) -> Session:
        """Load a session or create a new one if it doesn't exist."""
        path = self._get_path(session_id)

        if path.exists():
            try:
                async with aiofiles.open(path, "r") as f:
                    content = await f.read()
                    data = json.loads(content)
                    return Session(**data)
            except Exception as e:
                logger.error(f"Failed to load session {session_id}: {e}")
                # Fallback to new session on corruption? Or raise?
                # For robustness, maybe backup corrupt file and start new?
                # Let's start new for now.
                pass

        # Create new
        logger.info(f"Creating new session: {session_id}")
        return Session(id=session_id)

    async def save_session(self, session: Session) -> None:
        """Persist session to disk."""
        if session.ephemeral:
            return

        try:
            path = self._get_path(session.id)
            data = session.model_dump_json(indent=2)
            async with aiofiles.open(path, "w") as f:
                await f.write(data)
        except Exception as e:
            logger.error(f"Failed to save session {session.id}: {e}")

    def list_sessions(self) -> list[str]:
        # Sync method for quick listing
        return [f.stem for f in self.storage_dir.glob("*.json")]


# Singleton
session_store = SessionManager()

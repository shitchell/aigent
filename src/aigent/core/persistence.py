import json
from .. import __version__
from pathlib import Path
from typing import List, Optional, Dict, Any
from langchain_core.messages import messages_to_dict, messages_from_dict, BaseMessage
import aiofiles

class SessionManager:
    """
    Manages storage and retrieval of agent session history.
    """
    def __init__(self, storage_dir: Path):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, session_id: str) -> Path:
        # Basic sanitization to prevent directory traversal
        safe_id = Path(session_id).name
        return self.storage_dir / f"{safe_id}.json"

    async def save_session(self, session_id: str, profile_name: str, history: List[BaseMessage]) -> None:
        """
        Asynchronously saves the session state to disk.
        """
        try:
            data = {
                "profile": profile_name,
                "history": messages_to_dict(history),
                "version": __version__
            }
            async with aiofiles.open(self._get_path(session_id), "w") as f:
                await f.write(json.dumps(data, indent=2))
        except Exception as e:
            print(f"Error saving session {session_id}: {e}")

    async def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Loads session data. Returns a dict containing 'profile' and 'history' (messages).
        Returns None if session does not exist.
        """
        path = self._get_path(session_id)
        if not path.exists():
            return None
        
        try:
            async with aiofiles.open(path, "r") as f:
                content = await f.read()
                data = json.loads(content)
                
            # Backwards compatibility for old format (list of messages)
            if isinstance(data, list):
                return {
                    "profile": "default",
                    "history": messages_from_dict(data)
                }
            
            # Convert dict history back to objects
            if "history" in data:
                data["history"] = messages_from_dict(data["history"])
                
            return data
        except Exception as e:
            print(f"Error loading session {session_id}: {e}")
            return None

    def list_sessions(self) -> List[str]:
        """
        Returns a list of session IDs sorted by modification time (newest first).
        """
        try:
            files = list(self.storage_dir.glob("*.json"))
            # Sort by mtime desc
            files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            return [f.stem for f in files]
        except Exception:
            return []

    def delete_session(self, session_id: str) -> bool:
        """Deletes a session file."""
        try:
            path = self._get_path(session_id)
            if path.exists():
                path.unlink()
                return True
            return False
        except Exception:
            return False

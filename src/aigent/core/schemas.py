"""Core Pydantic Models for Aigent V2.

This module defines the strict data structures used for event payloads
and system state.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

try:
    from enum import StrEnum
except ImportError:
    from strenum import StrEnum

from pydantic import BaseModel, Field

class ClientType(StrEnum):
    WEB = "web"
    TUI = "tui"
    REPL = "repl"
    UNKNOWN = "unknown"

class RoleType(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"

class User(BaseModel):
    """Represents a connected user."""
    id: str
    name: str
    client_type: ClientType = ClientType.UNKNOWN
    
    @classmethod
    def create(cls, name: str, client_type: ClientType) -> "User":
        return cls(id=str(uuid4()), name=name, client_type=client_type)

class Message(BaseModel):
    """A single message in the conversation history."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: float = Field(default_factory=lambda: datetime.now().timestamp())
    role: RoleType
    content: str
    # Metadata can store tool calls, approval IDs, etc.
    metadata: Dict[str, Any] = Field(default_factory=dict)

class Session(BaseModel):
    """Represents a persistent chat session."""
    id: str
    name: Optional[str] = None
    created_at: float = Field(default_factory=lambda: datetime.now().timestamp())
    updated_at: float = Field(default_factory=lambda: datetime.now().timestamp())
    history: List[Message] = Field(default_factory=list)
    
    # Session Settings (could be its own model)
    locked: bool = False
    ephemeral: bool = False
    
    def add_message(self, message: Message) -> None:
        self.history.append(message)
        self.updated_at = datetime.now().timestamp()

# --- Event Payloads ---

class ClientInput(BaseModel):
    """Payload for CLIENT_INPUT_RECEIVED."""
    content: str
    # Optional metadata from the client (e.g. client timestamp)
    meta: Dict[str, Any] = Field(default_factory=dict)

class ToolRequest(BaseModel):
    """Payload for tool execution requests."""
    tool_name: str
    tool_input: Dict[str, Any]
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    tool_call_id: Optional[str] = None # LangChain ID

class ApprovalRequest(BaseModel):
    """Payload for approval:requested."""
    request_id: str
    tool_name: str
    tool_input: Dict[str, Any]

class ApprovalResponse(BaseModel):
    """Payload for approval:response."""
    request_id: str
    decision: str # "allow", "deny", "always"
    user_id: str

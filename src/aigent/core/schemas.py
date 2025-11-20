from enum import StrEnum
from pydantic import BaseModel, Field
from typing import Literal, Optional, Any, Dict, List

class EventType(StrEnum):
    SYSTEM = "system"
    USER_INPUT = "user_input"
    TOKEN = "token"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    ERROR = "error"
    THOUGHT = "thought"
    FINISH = "finish"
    # New events for authorization
    APPROVAL_REQUEST = "approval_request"
    APPROVAL_RESPONSE = "approval_response"

class PermissionPolicy(StrEnum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"

class PermissionSchema(BaseModel):
    name: str
    default_policy: PermissionPolicy = PermissionPolicy.ASK
    tools: Dict[str, PermissionPolicy] = Field(default_factory=dict)

class AgentEvent(BaseModel):
    """
    The fundamental unit of communication in the system.
    Everything from a user typing to the LLM thinking is an Event.
    """
    type: EventType
    content: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Helper for web sockets (Pydantic v2)
    def to_json(self) -> str:
        return self.model_dump_json()

class ModelProvider(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    GROK = "grok"

class UserProfile(BaseModel):
    """
    Defines the configuration for a specific agent 'persona'.
    Loaded from ~/.config/aigent/settings.yaml
    """
    name: str
    system_prompt: Optional[str] = None
    system_prompt_path: Optional[str] = None # Deprecated, maps to system_prompt_files
    system_prompt_files: List[str] = Field(default_factory=list)
    context_files: List[str] = Field(default_factory=list)
    
    model_provider: ModelProvider = ModelProvider.OPENAI
    model_name: str = "gpt-4o"
    temperature: float = 0.7
    allowed_tools: List[str] = Field(default_factory=lambda: ["*"])
    # Link to a permission schema
    permission_schema: str = "default"
    
class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    static_dir: str = "static"

class AgentConfig(BaseModel):
    """
    Global application configuration.
    """
    default_profile: str = "default"
    plugin_dir: str = "~/.aigent/tools"
    tool_call_preview_length: int = 100
    
    # Server Configuration
    server: ServerConfig = Field(default_factory=ServerConfig)
    
    # Security: Path Restrictions
    # List of allowed root directories for file operations.
    # Default is ["."] which resolves to CWD.
    allowed_work_dirs: List[str] = Field(default_factory=lambda: ["."])
    
    # Permission Schemas definitions
    permission_schemas: List[PermissionSchema] = Field(default_factory=lambda: [
        PermissionSchema(name="default", default_policy=PermissionPolicy.ASK, tools={"fs_read": PermissionPolicy.ALLOW})
    ])

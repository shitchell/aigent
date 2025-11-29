"""Profile Manager.

Handles loading configuration and user profiles from settings.yaml.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Any

import yaml
from pydantic import BaseModel, Field

from aigent.core.logging import get_logger

logger = get_logger(__name__)

# Paths
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "aigent" / "settings.yaml"
# Legacy/Example paths could be checked too

class PermissionSchema(BaseModel):
    name: str
    default_policy: str # "allow", "deny", "ask"
    tools: Dict[str, str] = Field(default_factory=dict)

class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    static_dir: str = "static"

class Profile(BaseModel):
    name: str
    model_provider: str
    model_name: str
    temperature: float = 0.7
    allowed_tools: List[str] = Field(default_factory=list)
    permission_schema: str = "default"
    system_prompt: Optional[str] = None # Inline override

class Settings(BaseModel):
    default_profile: str = "default"
    plugin_dir: str = "~/.aigent/tools/"
    tool_call_preview_length: int = 200
    allowed_work_dirs: List[str] = Field(default_factory=lambda: ["."])

class Config(BaseModel):
    settings: Settings = Field(default_factory=Settings)
    server: ServerConfig = Field(default_factory=ServerConfig)
    permission_schemas: List[PermissionSchema] = Field(default_factory=list)
    profiles: Dict[str, Profile] = Field(default_factory=dict)

class ProfileManager:
    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH):
        self.config_path = config_path
        self.config = Config()
        self.loaded = False

    def load(self) -> None:
        if not self.config_path.exists():
            logger.warning(f"Config not found at {self.config_path}, using defaults.")
            self.loaded = True
            return

        try:
            with open(self.config_path, "r") as f:
                data = yaml.safe_load(f)
            self.config = Config(**data)
            self.loaded = True
            logger.info(f"Loaded config from {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")

    def get_profile(self, name: str) -> Profile:
        if not self.loaded:
            self.load()
        
        # Fallback to default if not found
        if name not in self.config.profiles:
            if name != self.config.settings.default_profile:
                logger.warning(f"Profile '{name}' not found, trying default.")
                name = self.config.settings.default_profile
            
            if name not in self.config.profiles:
                # Emergency fallback
                return Profile(name="fallback", model_provider="openai", model_name="gpt-4o")
        
        return self.config.profiles[name]

    def get_permission_policy(self, schema_name: str, tool_name: str) -> str:
        if not self.loaded:
            self.load()
            
        schema = next((s for s in self.config.permission_schemas if s.name == schema_name), None)
        if not schema:
            return "ask" # Safe default
            
        return schema.tools.get(tool_name, schema.default_policy)

# Singleton
profiles = ProfileManager()

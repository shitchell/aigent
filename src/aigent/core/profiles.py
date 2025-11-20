import os
import yaml
from typing import Dict, Optional
from pathlib import Path
from aigent.core.schemas import UserProfile

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "aigent" / "profiles.yaml"

class ProfileManager:
    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH):
        self.config_path = config_path
        self._profiles: Dict[str, UserProfile] = {}
        self.loaded = False

    def load_profiles(self) -> None:
        """
        Loads profiles from the YAML configuration file.
        If the file doesn't exist, it creates a default profile in memory.
        """
        if not self.config_path.exists():
            # Return a default profile if config doesn't exist
            self._profiles = {"default": UserProfile(name="default")}
            self.loaded = True
            return

        try:
            with open(self.config_path, "r") as f:
                data = yaml.safe_load(f) or {}
                
            # Expecting a dict structure: { "profiles": { "name": { ... } } }
            # or just a list of profiles. Let's assume a dict of named profiles for simplicity.
            profiles_data = data.get("profiles", {})
            
            for name, profile_data in profiles_data.items():
                # inject name from key if missing
                if "name" not in profile_data:
                    profile_data["name"] = name
                
                self._profiles[name] = UserProfile(**profile_data)
                
            # Ensure default exists
            if "default" not in self._profiles:
                self._profiles["default"] = UserProfile(name="default")
                
        except Exception as e:
            raise ValueError(f"Failed to parse profiles from {self.config_path}: {e}")
            
        self.loaded = True

    def get_profile(self, name: str) -> UserProfile:
        if not self.loaded:
            self.load_profiles()
            
        if name not in self._profiles:
            raise KeyError(f"Profile '{name}' not found. Available: {list(self._profiles.keys())}")
            
        return self._profiles[name]

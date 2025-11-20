import pytest
from pathlib import Path
from aigent.core.profiles import ProfileManager
from aigent.core.schemas import UserProfile

def test_default_profile_creation(tmp_path):
    # Point to a non-existent config file
    config_path = tmp_path / "profiles.yaml"
    pm = ProfileManager(config_path=config_path)
    
    profile = pm.get_profile("default")
    assert profile.name == "default"
    assert profile.model_provider == "openai"

def test_load_custom_profile(tmp_path):
    config_path = tmp_path / "profiles.yaml"
    yaml_content = """
profiles:
  coder:
    model_provider: anthropic
    temperature: 0.1
"""
    config_path.write_text(yaml_content)
    
    pm = ProfileManager(config_path=config_path)
    profile = pm.get_profile("coder")
    
    assert profile.name == "coder"
    assert profile.model_provider == "anthropic"
    assert profile.temperature == 0.1

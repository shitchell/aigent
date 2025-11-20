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

def test_profile_path_resolution(tmp_path):
    config_path = tmp_path / "config" / "profiles.yaml"
    config_path.parent.mkdir()
    
    # Create a dummy prompt file relative to config
    prompt_file = config_path.parent / "prompt.md"
    prompt_file.write_text("Be helpful.")
    
    yaml_content = f"""
profiles:
  test:
    system_prompt_files:
      - "./prompt.md"
    context_files:
      - "~/foo.md"
    system_prompt: "Inline instruction."
"""
    config_path.write_text(yaml_content)
    
    pm = ProfileManager(config_path=config_path)
    profile = pm.get_profile("test")
    
    # Check absolute resolution
    assert str(prompt_file) in profile.system_prompt_files[0]
    assert profile.system_prompt == "Inline instruction."
    # Check home expansion (simple check if it no longer starts with ~)
    assert not profile.context_files[0].startswith("~")
    assert "foo.md" in profile.context_files[0]

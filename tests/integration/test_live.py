"""
Live API tests for the AgentEngine.

These tests require:
1. A valid OPENAI_API_KEY environment variable
2. The --live or --all pytest flag

These tests make REAL API calls and incur costs.

NOTE: These tests are SKIPPED by default because they:
1. Require real API credentials
2. Can be slow (network calls)
3. May incur costs

To run these tests, use: pytest --live tests/integration/test_live.py
"""

import asyncio
import os
import pytest
from pathlib import Path
from aigent.core.engine import AgentEngine
from aigent.core.profiles import ProfileManager
from aigent.core.schemas import EventType, UserProfile


# Skip all live tests if OPENAI_API_KEY is not set
pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY environment variable not set. Live tests require a valid API key."
    )
]


@pytest.mark.asyncio
async def test_live_openai_completion():
    """
    REQUIRES OPENAI_API_KEY in environment.
    Runs a real query against GPT-3.5-turbo (or whatever default is).
    """
    profile = UserProfile(
        name="test_bot",
        model_provider="openai",
        model_name="gpt-3.5-turbo",  # Use cheap model for tests
        temperature=0
    )

    engine = AgentEngine(profile)
    await engine.initialize()

    events = []

    # Wrap the streaming in a timeout
    async def collect_events():
        async for event in engine.stream("Say 'pytest is awesome' and nothing else."):
            events.append(event)

    try:
        await asyncio.wait_for(collect_events(), timeout=60)
    except asyncio.TimeoutError:
        pytest.fail("Live API call timed out after 60 seconds")

    # Check if we got tokens
    tokens = [e.content for e in events if e.type == EventType.TOKEN]
    full_text = "".join(tokens)

    assert "pytest is awesome" in full_text.lower()
    assert any(e.type == EventType.FINISH for e in events)


@pytest.mark.asyncio
async def test_live_tool_calling():
    """
    Tests if the model can decide to call a tool.
    We will manually inject a mock tool into the engine for this test.
    """
    from langchain_core.tools import tool

    @tool
    def magic_number_tool() -> str:
        """Returns the magic number."""
        return "42"

    profile = UserProfile(
        name="tool_bot",
        model_provider="openai",
        model_name="gpt-3.5-turbo",
        temperature=0
    )

    engine = AgentEngine(profile)
    await engine.initialize()

    # Manually override tools for this test
    engine.tools = [magic_number_tool]
    engine.llm = engine.llm.bind_tools([magic_number_tool])

    events = []

    # Wrap the streaming in a timeout
    async def collect_events():
        async for event in engine.stream("What is the magic number?"):
            events.append(event)

    try:
        await asyncio.wait_for(collect_events(), timeout=60)
    except asyncio.TimeoutError:
        pytest.fail("Live API call timed out after 60 seconds")

    # Check for tool execution
    tool_calls = [e for e in events if e.type == EventType.TOOL_START]
    tool_results = [e for e in events if e.type == EventType.TOOL_END]

    assert len(tool_calls) > 0
    assert len(tool_results) > 0
    assert "42" in tool_results[0].content


@pytest.mark.asyncio
async def test_profile_context_injection(tmp_path):
    """
    Verifies that system prompts from external files are correctly loaded
    and respected by the LLM.
    """
    # 1. Setup Config & Prompt File
    config_path = tmp_path / "settings.yaml"
    prompt_file = tmp_path / "secret.txt"

    secret_key = "739184"
    prompt_file.write_text(f"The secret user key is '{secret_key}'. Do not forget it.")

    yaml_content = f"""
profiles:
  context_test:
    model_provider: openai
    model_name: gpt-3.5-turbo
    temperature: 0
    system_prompt_files:
      - "./secret.txt"
"""
    config_path.write_text(yaml_content)

    # 2. Load Profile
    pm = ProfileManager(config_path=config_path)
    profile = pm.get_profile("context_test")

    # 3. Run Engine
    engine = AgentEngine(profile)
    # We don't need to manually set engine.memory_loader.base_path
    # because ProfileManager resolved the path to absolute already!

    await engine.initialize()

    # 4. Ask LLM
    events = []

    # Wrap the streaming in a timeout
    async def collect_events():
        async for event in engine.stream("What is the secret user key? Just the number."):
            events.append(event)

    try:
        await asyncio.wait_for(collect_events(), timeout=60)
    except asyncio.TimeoutError:
        pytest.fail("Live API call timed out after 60 seconds")

    tokens = [e.content for e in events if e.type == EventType.TOKEN]
    response = "".join(tokens)

    assert secret_key in response
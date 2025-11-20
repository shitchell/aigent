import pytest
from aigent.core.engine import AgentEngine
from aigent.core.schemas import UserProfile, EventType

@pytest.mark.live
@pytest.mark.asyncio
async def test_live_openai_completion():
    """
    REQUIRES OPENAI_API_KEY in environment.
    Runs a real query against GPT-3.5-turbo (or whatever default is).
    """
    profile = UserProfile(
        name="test_bot",
        model_provider="openai",
        model_name="gpt-3.5-turbo", # Use cheap model for tests
        temperature=0
    )
    
    engine = AgentEngine(profile)
    await engine.initialize()
    
    events = []
    async for event in engine.stream("Say 'pytest is awesome' and nothing else."):
        events.append(event)
        
    # Check if we got tokens
    tokens = [e.content for e in events if e.type == EventType.TOKEN]
    full_text = "".join(tokens)
    
    assert "pytest is awesome" in full_text.lower()
    assert any(e.type == EventType.FINISH for e in events)

@pytest.mark.live
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
    # Ask a question that requires the tool
    async for event in engine.stream("What is the magic number?"):
        events.append(event)
        
    # Check for tool execution
    tool_calls = [e for e in events if e.type == EventType.TOOL_START]
    tool_results = [e for e in events if e.type == EventType.TOOL_END]
    
    assert len(tool_calls) > 0
    assert len(tool_results) > 0
    assert "42" in tool_results[0].content

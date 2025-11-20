import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from aigent.core.engine import AgentEngine
from aigent.core.schemas import UserProfile, EventType
from langchain_core.messages import HumanMessage, AIMessage

@pytest.fixture
def mock_profile():
    return UserProfile(name="test", model_provider="openai", model_name="gpt-4o-mini")

@pytest.mark.asyncio
async def test_engine_initialization(mock_profile):
    with patch("aigent.core.engine.ChatOpenAI") as MockLLM:
        engine = AgentEngine(mock_profile)
        await engine.initialize()
        
        assert len(engine.history) == 1
        assert "System" in str(type(engine.history[0]))
        MockLLM.assert_called_once()

@pytest.mark.asyncio
async def test_engine_stream_captures_history(mock_profile):
    """
    Crucial test: Verifies that the stream method captures the final output
    and appends it to self.history.
    """
    engine = AgentEngine(mock_profile)
    engine.llm = MagicMock() # Mock the LLM
    
    # Manually prep history
    engine.history = []

    # Mock AgentExecutor and its astream_events
    # We simulate the stream of events that LangChain produces
    mock_events = [
        {"event": "on_chat_model_stream", "data": {"chunk": MagicMock(content="Hello")}},
        {"event": "on_chat_model_stream", "data": {"chunk": MagicMock(content=" World")}},
        {
            "event": "on_chain_end", 
            "name": "AgentExecutor", 
            "data": {
                "output": {
                    "output": "Hello World", 
                    "intermediate_steps": []
                }
            }
        }
    ]

    async def mock_astream(*args, **kwargs):
        for event in mock_events:
            yield event
    
    # We must patch where it is imported FROM because it is a local import inside the method
    with patch("langchain.agents.create_tool_calling_agent"), \
         patch("langchain.agents.AgentExecutor") as MockExecutor:
         
        instance = MockExecutor.return_value
        instance.astream_events = mock_astream
        
        # Run the stream
        events = []
        async for event in engine.stream("Hi"):
            events.append(event)

    # Verify Events
    assert len(events) == 3 # Token, Token, Finish
    assert events[0].content == "Hello"
    assert events[2].type == EventType.FINISH
    
    # Verify History Capture (The Fix)
    # History should have: [HumanMessage("Hi"), AIMessage("Hello World")]
    assert len(engine.history) == 2
    assert isinstance(engine.history[0], HumanMessage)
    assert engine.history[0].content == "Hi"
    assert isinstance(engine.history[1], AIMessage)
    assert engine.history[1].content == "Hello World"

@pytest.mark.asyncio
async def test_stream_persists_user_name(mock_profile):
    engine = AgentEngine(mock_profile)
    engine.llm = MagicMock()
    engine.history = []
    
    # We don't need to mock execution fully, just start stream
    # But stream waits for task.
    # So we need minimal mock.
    
    async def mock_astream(*args, **kwargs):
        yield {"event": "on_chat_model_stream", "data": {"chunk": MagicMock(content="Hi")}}
        yield {"event": "on_chain_end", "name": "AgentExecutor", "data": {"output": {"output": "Hi"}}}

    with patch("langchain.agents.create_tool_calling_agent"), \
         patch("langchain.agents.AgentExecutor") as MockExecutor:
         
        instance = MockExecutor.return_value
        instance.astream_events = mock_astream
        
        async for event in engine.stream("Hello Aigent", user_name="Bob"):
            pass
            
        # Check History
        assert len(engine.history) == 2
        human_msg = engine.history[0]
        assert isinstance(human_msg, HumanMessage)
        assert human_msg.content == "Hello Aigent"
        assert human_msg.name == "Bob"

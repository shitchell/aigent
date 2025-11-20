import pytest
import asyncio
from aigent.core.bus import EventBus
from aigent.core.schemas import AgentEvent, EventType

@pytest.mark.asyncio
async def test_event_bus_subscription():
    bus = EventBus()
    received = []

    async def handler(event: AgentEvent):
        received.append(event)

    bus.subscribe(EventType.TOKEN, handler)
    
    # Publish matching event
    event = AgentEvent(type=EventType.TOKEN, content="hello")
    await bus.publish(event)
    
    assert len(received) == 1
    assert received[0].content == "hello"

@pytest.mark.asyncio
async def test_event_bus_ignore_unsubscribed():
    bus = EventBus()
    received = []

    async def handler(event: AgentEvent):
        received.append(event)

    bus.subscribe(EventType.TOKEN, handler)
    
    # Publish NON-matching event
    event = AgentEvent(type=EventType.ERROR, content="oops")
    await bus.publish(event)
    
    assert len(received) == 0

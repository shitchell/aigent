import pytest
import asyncio
from typing import Any
from aigent.core.events import Dispatcher, handles

@pytest.fixture
def bus():
    return Dispatcher()

class MockSession:
    id = "123"

class MockUser:
    name = "Tester"

@pytest.mark.asyncio
async def test_dependency_injection_objects(bus):
    """Test injecting objects by type."""
    
    received = {}
    
    # Define handler
    async def my_handler(session: MockSession, user: MockUser):
        received["session"] = session
        received["user"] = user
    
    bus.register("test:event", my_handler)
    
    # Dispatch
    s = MockSession()
    u = MockUser()
    
    await bus.dispatch("test:event", payload_session=s, payload_user=u)
    
    assert received["session"] is s
    assert received["user"] is u

@pytest.mark.asyncio
async def test_dependency_injection_primitives(bus):
    """Test injecting primitives by name."""
    
    received = {}
    
    async def my_handler(count: int, flag: bool):
        received["count"] = count
        received["flag"] = flag
        
    bus.register("test:prim", my_handler)
    
    await bus.dispatch("test:prim", count=42, flag=True, ignored="ignored")
    
    assert received["count"] == 42
    assert received["flag"] is True

@pytest.mark.asyncio
async def test_missing_dependency(bus):
    """Test that handler is skipped if dependency missing."""
    
    called = False
    async def my_handler(required: int):
        nonlocal called
        called = True
        
    bus.register("test:missing", my_handler)
    
    # Dispatch without 'required'
    await bus.dispatch("test:missing", other=1)
    
    assert not called

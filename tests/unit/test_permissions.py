import pytest
import asyncio
from aigent.core.permissions import Authorizer, AuthorizationStrategy, PermissionSchema, PermissionPolicy
from aigent.core.schemas import AgentEvent, EventType

@pytest.mark.asyncio
async def test_bash_strategy():
    strat = AuthorizationStrategy.bash_command
    
    # Simple cases
    assert strat("bash_execute", {"command": "ls -la"}) == "bash:ls"
    assert strat("bash_execute", {"command": "grep foo bar"}) == "bash:grep"
    
    # Env vars
    assert strat("bash_execute", {"command": "FOO=bar ls"}) == "bash:ls"
    
    # Prefixes
    assert strat("bash_execute", {"command": "sudo ls"}) == "bash:ls"
    # assert strat("bash_execute", {"command": "timeout 5s ping google.com"}) == "bash:ping"
    
    # Complex/Unsafe cases (should return None)
    assert strat("bash_execute", {"command": "ls && rm -rf /"}) is None
    assert strat("bash_execute", {"command": "ls | grep foo"}) is None
    assert strat("bash_execute", {"command": "ls > out.txt"}) is None

@pytest.mark.asyncio
async def test_authorizer_policy():
    # Setup Callback
    events = []
    async def callback(event):
        events.append(event)

    schema = PermissionSchema(
        name="test", 
        default_policy=PermissionPolicy.ASK,
        tools={
            "safe_tool": PermissionPolicy.ALLOW,
            "bad_tool": PermissionPolicy.DENY
        }
    )
    
    auth = Authorizer(schema, callback)
    
    # 1. ALLOW policy
    assert await auth.check("safe_tool", {}) is True
    assert len(events) == 0
    
    # 2. DENY policy
    assert await auth.check("bad_tool", {}) is False
    assert len(events) == 0
    
    # 3. ASK policy (Default)
    # Run check in background task because it awaits
    task = asyncio.create_task(auth.check("unknown_tool", {"x": 1}))
    
    # Wait for event emission
    await asyncio.sleep(0.01)
    assert len(events) == 1
    event = events[0]
    assert event.type == EventType.APPROVAL_REQUEST
    assert event.metadata["tool"] == "unknown_tool"
    
    # Resolve request
    req_id = event.metadata["request_id"]
    auth.resolve_request(req_id, {"decision": "allow"})
    
    # Task should complete now
    result = await task
    assert result is True

@pytest.mark.asyncio
async def test_authorizer_always_allow():
    events = []
    async def callback(event):
        events.append(event)

    schema = PermissionSchema(name="test", default_policy=PermissionPolicy.ASK)
    auth = Authorizer(schema, callback)
    
    # 1. Ask first time
    task = asyncio.create_task(auth.check("my_tool", {"arg": "1"}))
    await asyncio.sleep(0.01)
    req_id = events[0].metadata["request_id"]
    
    # Approve with "always_tool"
    auth.resolve_request(req_id, {"decision": "always_tool"})
    assert await task is True
    
    # 2. Check second time (should be instant allow)
    events.clear()
    assert await auth.check("my_tool", {"arg": "2"}) is True
    assert len(events) == 0

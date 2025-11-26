# Test Fixes Report

Date: November 25, 2025

## Summary

All tests in the following files have been fixed and are now passing:

- `tests/unit/test_cli_rendering.py` (8 tests)
- `tests/unit/test_websocket_logic.py` (9 tests)
- `tests/integration/test_server_startup.py` (7 tests)
- `tests/integration/test_session_switching.py` (6 tests)

**Total: 30 tests passing**

## Fixes Applied

### 1. test_cli_rendering.py

**Issue:** Tests were patching `sys.stdout.write`, `sys.stdout.flush`, and `builtins.print` but the actual CLI implementation uses `prompt_toolkit.print_formatted_text`.

**Fix:** Changed all mock patches to use `prompt_toolkit.print_formatted_text` instead.

**Tests affected:**
- `test_token_buffering`
- `test_ready_for_input_synchronization`
- `test_no_ansi_in_token_output`
- `test_tool_output_formatting`
- `test_approval_request_sets_ready`

**Changes:**
```python
# Before
with patch('sys.stdout.write', side_effect=lambda x: captured_writes.append(x)):
    with patch('sys.stdout.flush'):
        await ws_listener(mock_ws, mock_config, ready_event)

# After
with patch('prompt_toolkit.print_formatted_text', side_effect=capture_print):
    await ws_listener(mock_ws, mock_config, ready_event)
```

### 2. test_websocket_logic.py

**Issue:**
1. Tests were creating local `ConnectionManager()` instances but the `process_chat_message` function uses the global `manager` from the api module.
2. Tests were using `AsyncMock` for the engine object, but a `MagicMock` is required since only specific methods are async.

**Fix:**
1. Import and use the global `manager` from `aigent.server.api`
2. Use `MagicMock` for the engine object with async generator methods
3. Added cleanup code to remove test data from global manager after each test

**Tests affected:**
- `test_token_event_generation`
- `test_concurrent_session_locks`
- `test_error_event_on_exception`

**Changes:**
```python
# Before
manager = ConnectionManager()
mock_engine = AsyncMock()

# After
from aigent.server.api import manager
mock_engine = MagicMock()
mock_engine.stream = mock_stream  # async generator function

# Cleanup after test
del manager.sessions[session_id]
del manager.locks[session_id]
del manager.active_connections[session_id]
```

### 3. test_server_startup.py

**Issue:** The `test_kill_server_command` test was using a non-default port (18006) but the `kill-server` command reads the port from config defaults (8000).

**Fix:**
1. Changed test to use default port 8000
2. Added pre-check to kill any existing server on port 8000
3. Added proper output assertion for kill command success

**Changes:**
```python
# Before
port = 18006
proc = subprocess.Popen(
    [sys.executable, "-m", "aigent.main", "serve", "--port", str(port)],
    ...
)

# After
port = 8000  # Use default port since kill-server uses config defaults

# First check if a server is already running on default port
try:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://localhost:{port}/api/stats", timeout=1.0)
        if resp.status_code == 200:
            subprocess.run([sys.executable, "-m", "aigent.main", "kill-server"], timeout=5)
            await asyncio.sleep(2)
except:
    pass

# Use default port for server
proc = subprocess.Popen(
    [sys.executable, "-m", "aigent.main", "serve"],  # No explicit port
    ...
)
```

### 4. test_session_switching.py

**Issue:** Tests were not properly handling the history replay mechanism. When reconnecting to a session:
1. The server sends history replay events (including multiple FINISH events)
2. The test's `receive_until_finish` would stop at the first FINISH from history
3. Subsequent calls would get more history events instead of the new message

**Fix:**
1. Added `drain_all_messages()` helper method that collects all messages until no more arrive (timeout-based)
2. Updated reconnection tests to first drain all history, then send new message

**Tests affected:**
- `test_session_creation_and_switching`
- `test_session_persistence_across_reconnect`

**Changes:**
```python
# Added new helper method
async def drain_all_messages(self, ws, timeout: float = 0.5) -> List[dict]:
    """Drain all available messages until no more are coming (short timeout)."""
    messages = []
    while True:
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
            data = json.loads(msg)
            messages.append(data)
        except asyncio.TimeoutError:
            break
    return messages

# Updated test pattern
async with websockets.connect(ws1_url) as ws1:
    # Wait a moment for connection to stabilize
    await asyncio.sleep(0.2)

    # Drain ALL history replay messages (may include multiple FINISH events)
    history_messages = await self.drain_all_messages(ws1, timeout=2.0)

    # Verify history contains the original message
    # ...

    # Now send another message
    await ws1.send("Back to session 1")

    # This time receive_until_finish gets the new message's events
    messages = await self.receive_until_finish(ws1)
```

## Common Patterns Identified

1. **AsyncMock vs MagicMock**: Use `MagicMock` for the main object when only specific methods need to be async. Use async generator functions for `stream()` methods.

2. **Patch the actual implementation**: Always check what functions the source code actually calls and patch those, not what you assume it uses.

3. **Global state cleanup**: When tests modify global state (like the `manager` singleton), always clean up after the test.

4. **History replay handling**: When testing WebSocket reconnection, account for history replay events that may include multiple batches with their own FINISH events.

## Test Execution

```bash
# Run all fixed tests
python -m pytest tests/unit/test_cli_rendering.py \
                 tests/unit/test_websocket_logic.py \
                 tests/integration/test_server_startup.py \
                 tests/integration/test_session_switching.py -v

# Result: 30 passed, 2 warnings in ~80s
```

## Files Modified

- `tests/unit/test_cli_rendering.py`
- `tests/unit/test_websocket_logic.py`
- `tests/integration/test_server_startup.py`
- `tests/integration/test_session_switching.py` (newly modified in this session)

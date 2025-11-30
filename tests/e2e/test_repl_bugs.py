import pytest
import pexpect
import sys
import asyncio
import time

@pytest.mark.asyncio
async def test_repl_broadcast_missing(aigent_server):
    """
    Issue 2: REPL Client Missing Broadcasts.
    
    1. Spawn REPL A (Sender).
    2. Spawn REPL B (Receiver) on same session.
    3. REPL B waits at prompt.
    4. REPL A sends message.
    5. REPL B should show message WITHOUT pressing Enter.
    """
    base_url = aigent_server.replace("ws://", "")
    host, port = base_url.split(":")
    
    cmd = f"aigent chat --repl --host {host} --port {port} --session shared-repl-bug"
    
    # Spawn Clients
    repl_a = pexpect.spawn(cmd, encoding='utf-8', timeout=10)
    repl_b = pexpect.spawn(cmd, encoding='utf-8', timeout=10)
    
    # Wait for connection
    repl_a.expect("Connected")
    repl_a.expect(">")
    
    repl_b.expect("Connected")
    repl_b.expect(">")
    
    # Send from A
    repl_a.sendline("Message from A")
    
    # Check B
    # We expect to see "Message from A" immediately
    try:
        repl_b.expect("Message from A", timeout=2)
    except pexpect.TIMEOUT:
        pytest.fail("REPL B did not receive broadcast (Issue 2 reproduced)")
        
    repl_a.close()
    repl_b.close()

@pytest.mark.asyncio
async def test_repl_prompt_interleaving(aigent_server):
    """
    Issue 3: REPL Prompt Interleaved with Output.
    
    1. Spawn REPL.
    2. Send message.
    3. Expect response.
    4. Verify prompt `>` does not appear BEFORE response.
    """
    base_url = aigent_server.replace("ws://", "")
    host, port = base_url.split(":")
    
    cmd = f"aigent chat --repl --host {host} --port {port} --session repl-prompt-bug"
    repl = pexpect.spawn(cmd, encoding='utf-8', timeout=10)
    
    repl.expect("Connected")
    repl.expect(">")
    
    repl.sendline("Hello")
    
    # We expect to see the response (e.g. "Hello!"). 
    # But we want to ensure we DON'T see ">" before "Hello!".
    
    # Logic: Read everything until timeout or response.
    # If we see ">" before the response text, fail.
    
    index = repl.expect([">", "Hello"]) # Wait for Prompt OR Response part
    
    if index == 0:
        # We saw a prompt first! This is the bug.
        # But wait, we saw the initial prompt. We need to skip the *echo* of our command.
        pass
        
    # Validating exact interleaving with pexpect is tricky because of echo.
    # Pattern:
    # > Hello (Input Echo)
    # > (Buggy Prompt)
    # [Assistant] Hello...
    
    # Let's verify we see the response.
    try:
        repl.expect("Hello", timeout=5)
    except pexpect.TIMEOUT:
        pytest.fail("No response")
        
    # Now check what was before it? 
    # pexpect.before contains the text before the match.
    # If `>` is in `repl.before` (after our input echo), it's buggy.
    
    output = repl.before
    if ">" in output.strip():
        pytest.fail(f"Prompt appeared before response: {output} (Issue 3 reproduced)")
        
    repl.close()

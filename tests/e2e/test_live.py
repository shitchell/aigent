import pytest
import json
import websockets
import asyncio
import uuid

@pytest.mark.asyncio
async def test_live_chat_flow(aigent_server):
    """Test connecting, sending a message, and receiving tokens."""
    
    # Use 'default' profile (gpt-4o-mini)
    # Using random session ID to ensure fresh state
    session_id = f"e2e-{uuid.uuid4().hex[:8]}"
    uri = f"{aigent_server}/ws/chat/{session_id}?profile=default&user_id=tester"
    
    async with websockets.connect(uri) as ws:
        # 1. Send Message
        await ws.send("Hello Aigent")
        
        # 2. Collect Responses
        tokens = []
        user_echo = False
        
        try:
            # Read with timeout
            async with asyncio.timeout(10):
                async for message in ws:
                    data = json.loads(message)
                    typ = data.get("type")
                    
                    if typ == "user_input":
                        user_echo = True
                        assert data["content"] == "Hello Aigent"
                    
                    elif typ == "token":
                        tokens.append(data["content"])
                        
                    elif typ == "error":
                        pytest.fail(f"Server reported error: {data['content']}")
                        
                    elif typ == "finish":
                        break
                        
        except asyncio.TimeoutError:
            pytest.fail("Timed out waiting for response")
            
        # 3. Verify
        assert user_echo, "Did not receive user input echo"
        full_response = "".join(tokens)
        assert len(full_response) > 0, "No response from LLM"
        print(f"LLM Response: {full_response}")

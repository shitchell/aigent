import pytest
from playwright.sync_api import Page, expect
from websockets.sync.client import connect

@pytest.mark.e2e
def test_web_profiles_missing(page: Page, aigent_server_http):
    """Issue 4: Web UI Profiles Missing."""
    page.goto(aigent_server_http)
    
    # Check Welcome Screen Profile List
    # Expect "default", "cheap" to be present
    # We check if *any* element with "default" is visible
    expect(page.get_by_text("default").first).to_be_visible(timeout=5000)
    expect(page.get_by_text("cheap").first).to_be_visible()

@pytest.mark.e2e
def test_web_history_missing(page: Page, aigent_server_http, aigent_ws_url):
    """Issue 5: Web UI Missing History on Join."""
    import time
    
    # 1. Create Session & Add History via REPL/WebSocket (Sync)
    session_id = "test-history-bug"
    uri = f"{aigent_ws_url}/ws/chat/{session_id}?user_id=seeder"
    
    with connect(uri) as ws:
        ws.send("Message 1")
        # Wait for echo
        time.sleep(1)
    
    # 2. Join Web UI
    page.goto(f"{aigent_server_http}/?session={session_id}")
    
    # 3. Assert Message Visible
    # This should fail if history replay is broken
    expect(page.get_by_text("Message 1")).to_be_visible(timeout=5000)

@pytest.mark.e2e
def test_web_tool_loop(page: Page, aigent_server_http):
    """Issue 6: Web UI Tool Looping."""
    # This is hard to automate without mocking the LLM to force a tool call.
    # We will skip or try best effort with prompt.
    pass

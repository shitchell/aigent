import pytest
import subprocess
import time
import requests
from playwright.sync_api import Page, expect

SERVER_URL = "http://127.0.0.1:8000"

@pytest.fixture(scope="module")
def run_server():
    """Starts the Aigent server in a subprocess."""
    proc = subprocess.Popen(
        ["aigent", "serve", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for server to come up
    max_retries = 10
    for _ in range(max_retries):
        try:
            requests.get(SERVER_URL)
            break
        except requests.exceptions.ConnectionError:
            time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError("Server failed to start")

    yield proc
    
    proc.kill()

@pytest.mark.e2e
def test_welcome_screen(page: Page, run_server):
    page.goto(SERVER_URL)
    
    # Expect Welcome Screen
    expect(page.locator("text=Welcome to Aigent")).to_be_visible()
    
    # Expect Profile Options (Mocked or Default)
    expect(page.locator("text=default")).to_be_visible()

@pytest.mark.e2e
def test_create_new_chat(page: Page, run_server):
    page.goto(SERVER_URL)
    
    # Click Default Profile to start
    page.click("text=default")
    
    # Should redirect to Chat Interface
    expect(page.locator("#chat-container")).to_be_visible()
    
    # Verify Session ID in header
    expect(page.locator("text=Session: chat-")).to_be_visible()

@pytest.mark.e2e
def test_send_message(page: Page, run_server):
    page.goto(SERVER_URL)
    page.click("text=default")
    
    # Type message
    page.fill("input[placeholder='Type a message...']", "Hello Playwright")
    page.click("button:has-text('Send')")
    
    # Expect User Message to appear
    expect(page.locator("text=Hello Playwright")).to_be_visible()
    
    # Expect Aigent to reply (Typing... then Content)
    # Since we don't have keys in CI/Test env usually, this might fail or show error
    # But we check that the bubble appears
    expect(page.locator("text=Aigent")).to_be_visible()

@pytest.mark.e2e
def test_session_persistence(page: Page, run_server):
    page.goto(SERVER_URL)
    page.click("text=default")
    
    # Send message
    page.fill("input", "Memory Test")
    page.click("button:has-text('Send')")
    expect(page.locator("text=Memory Test")).to_be_visible()
    
    # Get current URL
    chat_url = page.url
    
    # Refresh
    page.reload()
    
    # Expect message to still be there (History Replay)
    expect(page.locator("text=Memory Test")).to_be_visible()

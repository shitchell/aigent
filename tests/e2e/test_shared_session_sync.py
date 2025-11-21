import pytest
import subprocess
import sys
import time
import requests
import os
import asyncio
from playwright.async_api import async_playwright, expect

SERVER_URL = "http://127.0.0.1:8000"

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_shared_session_sync():
    # Ensure no stale server
    
    # 1. Launch CLI
    cli_cmd = [sys.executable, "-m", "aigent.main", "chat", "--yolo"]
    
    print(f"Launching CLI: {cli_cmd}")
    cli_proc = subprocess.Popen(
        cli_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=0 # Unbuffered
    )
    
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        try:
            # 2. Wait for Server
            server_up = False
            for _ in range(20):
                try:
                    if requests.get(SERVER_URL).status_code == 200:
                        server_up = True
                        break
                except:
                    time.sleep(0.5)
            
            if not server_up:
                stdout, stderr = cli_proc.communicate(timeout=1)
                pytest.fail(f"Server failed to start. CLI Output:\n{stdout}\nStderr:\n{stderr}")

            # 3. Connect Web Client
            await page.goto(f"{SERVER_URL}/?session=cli-default")
            
            # 4. Send Message from CLI
            time.sleep(2) 
            cli_proc.stdin.write("Hello from CLI\n")
            cli_proc.stdin.flush()
            
            # 5. Verify in Web
            # Use .first to handle potential duplicates (e.g. if rendered twice or in history + stream)
            await expect(page.locator("text=Hello from CLI").first).to_be_visible(timeout=10000)
            
            # 6. Send Message from Web
            await page.fill('input[placeholder="Type a message..."]', "Hello from Web")
            await page.press('input[placeholder="Type a message..."]', "Enter")
            
            # 7. Verify round trip (LLM Response)
            await asyncio.sleep(2) # Give LLM time (mock/real)
            
        finally:
            cli_proc.terminate()
            await browser.close()

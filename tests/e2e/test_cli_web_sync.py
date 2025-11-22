"""
End-to-end test for CLI and Web synchronization.
Tests bidirectional communication between CLI and Web clients sharing a session.

This test uses real LLM calls to ensure complete integration.
"""

import asyncio
import sys
import os
import time
import re
import pytest
import pexpect
from pathlib import Path
from playwright.async_api import async_playwright, expect

# Test configuration
TEST_SESSION_ID = "e2e-test-session"
TEST_PROMPT = 'This is a test. Please do not make any tool calls. Only respond with the message "Test confirmed" -- no punctuation and no period.'
EXPECTED_RESPONSE = "Test confirmed"
SERVER_HOST = "localhost"
SERVER_PORT = 8000
TIMEOUT = 30  # seconds for LLM responses


class TestCLIWebSync:
    """Test suite for CLI-Web synchronization."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_full_bidirectional_sync(self):
        """
        Full E2E test flow:
        1. Launch CLI with specific session ID
        2. Launch Playwright and connect to web UI with same session
        3. CLI sends message
        4. Verify message appears in browser
        5. Wait for and verify LLM response in both
        6. Browser sends message
        7. Verify message appears in CLI
        8. Verify both receive second LLM response
        """

        # Step 1: Launch CLI
        cli_process = pexpect.spawn(
            f"{sys.executable} -m aigent.main chat --session {TEST_SESSION_ID}",
            encoding='utf-8',
            timeout=TIMEOUT,
            env={**os.environ, 'TERM': 'xterm'}
        )

        try:
            # Wait for CLI to be ready (look for prompt)
            cli_process.expect(r'>', timeout=10)
            print("✓ CLI launched and ready")

            # Step 2: Launch Playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                # Navigate to web UI with same session
                await page.goto(f"http://{SERVER_HOST}:{SERVER_PORT}/?session={TEST_SESSION_ID}")
                await page.wait_for_load_state("networkidle")
                print("✓ Browser connected to web UI")

                # Wait for WebSocket connection (look for some UI element that indicates ready)
                await page.wait_for_selector("#chat-input", timeout=5000)
                print("✓ WebSocket connected")

                # Step 3: Send message from CLI
                cli_message = "Hello from CLI. " + TEST_PROMPT
                cli_process.sendline(cli_message)
                print(f"→ CLI sent: {cli_message}")

                # Step 4: Verify message appears in browser
                # Look for the user message in the chat history
                user_msg_selector = f"text='{cli_message}'"
                await page.wait_for_selector(user_msg_selector, timeout=5000)
                print("✓ CLI message appeared in browser")

                # Step 5: Wait for LLM response in browser
                await page.wait_for_selector(f"text='{EXPECTED_RESPONSE}'", timeout=TIMEOUT*1000)
                print("✓ LLM response appeared in browser")

                # Verify LLM response in CLI
                cli_process.expect(EXPECTED_RESPONSE, timeout=TIMEOUT)
                print("✓ LLM response appeared in CLI")

                # Wait for next prompt in CLI
                cli_process.expect(r'>', timeout=5)

                # Step 6: Send message from browser
                browser_message = "Hello from Browser. " + TEST_PROMPT

                # Find and fill the input field
                input_field = await page.query_selector("#chat-input")
                await input_field.fill(browser_message)

                # Submit (either press Enter or click send button)
                await page.keyboard.press("Enter")
                print(f"→ Browser sent: {browser_message}")

                # Step 7: Verify message appears in CLI
                cli_process.expect(browser_message, timeout=5)
                print("✓ Browser message appeared in CLI")

                # Step 8: Verify both receive second LLM response
                # CLI should receive it
                cli_process.expect(EXPECTED_RESPONSE, timeout=TIMEOUT)
                print("✓ Second LLM response appeared in CLI")

                # Browser should also have it
                # Count occurrences - should be 2 now
                response_elements = await page.query_selector_all(f"text='{EXPECTED_RESPONSE}'")
                assert len(response_elements) == 2, f"Expected 2 responses, found {len(response_elements)}"
                print("✓ Second LLM response appeared in browser")

                # Cleanup
                await browser.close()

            # Exit CLI gracefully
            cli_process.sendline("/exit")
            cli_process.expect(pexpect.EOF, timeout=5)
            print("✓ Test completed successfully!")

        except pexpect.TIMEOUT as e:
            print(f"✗ Timeout waiting for: {e}")
            print(f"CLI output so far:\n{cli_process.before}")
            raise

        except Exception as e:
            print(f"✗ Test failed: {e}")
            print(f"CLI output:\n{cli_process.before}")
            raise

        finally:
            # Ensure CLI process is terminated
            if cli_process.isalive():
                cli_process.terminate()


    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_cli_output_quality(self):
        """
        Test that CLI output is clean without rendering artifacts.
        Uses pexpect to capture raw terminal output.
        """

        cli_process = pexpect.spawn(
            f"{sys.executable} -m aigent.main chat --session test-artifacts",
            encoding='utf-8',
            timeout=TIMEOUT,
            env={**os.environ, 'TERM': 'xterm'}
        )

        try:
            # Wait for prompt
            cli_process.expect(r'>', timeout=10)

            # Send test message
            cli_process.sendline(TEST_PROMPT)

            # Capture everything until next prompt
            cli_process.expect(r'>', timeout=TIMEOUT)
            output = cli_process.before

            # Check for rendering artifacts
            artifacts = []

            # Check for carriage returns not at line endings
            if '\r' in output and not all(c == '\n' for c in output.split('\r')[1:]):
                artifacts.append("Unexpected carriage returns found")

            # Check for ANSI cursor movement (beyond basic colors)
            cursor_patterns = [
                r'\x1b\[\d+[ABCD]',  # Cursor movement
                r'\x1b\[\d+;?\d*[HJ]',  # Cursor position/clear
                r'\x1b\[2K',  # Clear line
            ]
            for pattern in cursor_patterns:
                if re.search(pattern, output):
                    artifacts.append(f"Found cursor control pattern: {pattern}")

            # Check for malformed sequences
            if '?[' in output or '?25h' in output or '?25l' in output:
                artifacts.append("Malformed ANSI sequences found")

            # Check for Rich library artifacts
            if 'Window too small' in output:
                artifacts.append("Rich library error found")

            assert not artifacts, f"CLI output artifacts detected:\n" + "\n".join(artifacts)
            print("✓ CLI output is clean")

            # Exit cleanly
            cli_process.sendline("/exit")
            cli_process.expect(pexpect.EOF, timeout=5)

        finally:
            if cli_process.isalive():
                cli_process.terminate()


class TestHelpers:
    """Helper utilities for E2E tests."""

    @staticmethod
    async def wait_for_server(host: str = SERVER_HOST, port: int = SERVER_PORT, timeout: int = 10):
        """Wait for server to be available."""
        import httpx

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"http://{host}:{port}/")
                    if response.status_code == 200:
                        return True
            except Exception:
                pass
            await asyncio.sleep(0.5)

        raise TimeoutError(f"Server not available after {timeout} seconds")

    @staticmethod
    def extract_clean_text(raw_output: str) -> str:
        """Extract clean text from terminal output, removing ANSI codes."""
        # Remove ANSI escape sequences
        ansi_escape = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
        clean = ansi_escape.sub('', raw_output)

        # Remove other control characters except newline
        clean = ''.join(char for char in clean if char == '\n' or ord(char) >= 32)

        return clean.strip()


# Pytest configuration for E2E tests
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "e2e: End-to-end integration tests")


# Optional: Skip E2E tests by default (they cost tokens)
def pytest_collection_modifyitems(config, items):
    """Skip E2E tests unless explicitly requested."""
    if not config.getoption("--run-e2e", default=False):
        skip_e2e = pytest.mark.skip(reason="E2E tests skipped. Use --run-e2e to run them.")
        for item in items:
            if "e2e" in item.keywords:
                item.add_marker(skip_e2e)
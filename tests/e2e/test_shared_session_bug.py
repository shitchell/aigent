"""
Test for the shared session CLI output deletion bug.

BUG: When CLI is connected to a shared session and another client (e.g., web)
sends a message, the agent's response appears briefly on CLI then gets deleted
chunk by chunk due to carriage returns (\r).

ROOT CAUSE: The flush_tokens() function in cli.py uses print_formatted_text()
which, when called inside patch_stdout() while the prompt is active, produces
carriage return sequences that delete previously printed content.

FIX: Use sys.stdout.write() directly for token output instead of
print_formatted_text(), as it doesn't have this interaction issue.
"""

import asyncio
import subprocess
import sys
import os
import io
import pytest
import pexpect
import httpx
import websockets
import json
from unittest.mock import patch, MagicMock, AsyncMock


SERVER_HOST = "localhost"
SERVER_PORT = 8000
TEST_SESSION_ID = "shared-session-bug-test"
TEST_PROMPT = 'Say exactly "Hello World" with no other text.'
EXPECTED_RESPONSE = "Hello World"
TIMEOUT = 30


class TestSharedSessionBug:
    """
    E2E test suite for the shared session CLI output deletion bug.

    These tests require a running server and use pexpect for terminal capture.
    """

    @pytest.fixture
    async def test_server(self):
        """Fixture to spawn and manage test server."""
        # Kill any existing server
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://{SERVER_HOST}:{SERVER_PORT}/api/stats")
                if resp.status_code == 200:
                    subprocess.run([sys.executable, "-m", "aigent.main", "kill-server"], capture_output=True)
                    await asyncio.sleep(1)
        except:
            pass

        # Start server with YOLO mode
        server_proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "aigent.main", "serve",
            "--host", SERVER_HOST, "--port", str(SERVER_PORT), "--yolo",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Wait for server
        for i in range(20):
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"http://{SERVER_HOST}:{SERVER_PORT}/api/stats")
                    if resp.status_code == 200:
                        break
            except:
                pass
            await asyncio.sleep(0.5)
        else:
            server_proc.terminate()
            await server_proc.wait()
            pytest.fail("Server failed to start")

        print(f"[TEST] Server started on port {SERVER_PORT}")
        yield

        # Cleanup
        server_proc.terminate()
        try:
            await asyncio.wait_for(server_proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            server_proc.kill()
            await server_proc.wait()
        print("[TEST] Server stopped")

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_shared_session_output_no_carriage_returns(self, test_server):
        """
        Test that when another client sends a message, the CLI output
        does NOT contain excessive carriage returns that would delete text.

        This test FAILS with the bug present and PASSES after the fix.
        """

        # Step 1: Launch CLI with the session
        cli_process = pexpect.spawn(
            f"{sys.executable} -m aigent.main chat --session {TEST_SESSION_ID}",
            encoding='utf-8',
            timeout=TIMEOUT,
            env={**os.environ, 'TERM': 'xterm', 'COLUMNS': '120', 'LINES': '40'}
        )

        try:
            # Wait for CLI to connect
            index = cli_process.expect([r'>', 'Connected to Aigent Server'], timeout=15)
            if index == 1:
                cli_process.expect(r'>', timeout=10)
            print("[TEST] CLI connected and ready")

            # Step 2: Connect WebSocket client (simulating another user)
            ws_url = f"ws://{SERVER_HOST}:{SERVER_PORT}/ws/chat/{TEST_SESSION_ID}?user_id=web-user&profile=default"

            async with websockets.connect(ws_url) as ws:
                print("[TEST] WebSocket client connected to same session")

                # Give CLI time to stabilize
                await asyncio.sleep(1)

                # Step 3: Send message FROM WEBSOCKET (not CLI!)
                await ws.send(TEST_PROMPT)
                print(f"[TEST] WebSocket sent: {TEST_PROMPT}")

                # Step 4: Wait for CLI to receive and display the response
                all_output_parts = []
                try:
                    # First, we should see the other user's message
                    cli_process.expect(r'\[web-user\]', timeout=10)
                    all_output_parts.append(cli_process.before or "")
                    print("[TEST] CLI received other user's message notification")

                    # Wait a bit for the agent to start responding
                    await asyncio.sleep(2)

                    # Now wait for the agent's response and the next prompt
                    # The response should be visible BEFORE the prompt appears
                    cli_process.expect(r'>', timeout=TIMEOUT)
                    all_output_parts.append(cli_process.before or "")

                except pexpect.TIMEOUT:
                    all_output_parts.append(cli_process.before or "")
                    print(f"[TEST] Timeout occurred, partial output captured")

                # Get all output captured by pexpect
                raw_output = ''.join(all_output_parts)

                print(f"[TEST] Raw output length: {len(raw_output)}")
                print(f"[TEST] Raw output (first 300 chars): {repr(raw_output[:300])}")

                # Count carriage returns
                total_cr_count = raw_output.count('\r')
                print(f"[TEST] Total carriage return count: {total_cr_count}")

                # Check if the expected response is present
                has_response = EXPECTED_RESPONSE.lower() in raw_output.lower()
                print(f"[TEST] Has expected response '{EXPECTED_RESPONSE}': {has_response}")

                # THE KEY ASSERTION:
                # The agent's response must be visible in the output.
                # With the bug, the response would be printed then deleted by carriage returns.
                #
                # Note: We can't simply count all carriage returns because prompt_toolkit's
                # patch_stdout() legitimately uses \r sequences for cursor management.
                # Instead, we verify the response is present AND check for the specific
                # pattern of carriage returns AFTER the response (which would delete it).

                # First, verify the response is visible
                assert has_response, (
                    f"Expected response '{EXPECTED_RESPONSE}' not found in output.\n"
                    f"The response may have been deleted by carriage returns.\n"
                    f"Output: {repr(raw_output[:500])}"
                )

                # Find the position of the response in the output
                import re
                response_match = re.search(re.escape(EXPECTED_RESPONSE), raw_output, re.IGNORECASE)
                if response_match:
                    # Check for excessive carriage returns AFTER the response
                    # These would indicate the response is being deleted
                    after_response = raw_output[response_match.end():]
                    cr_after_response = after_response.count('\r')
                    print(f"[TEST] CRs after response: {cr_after_response}")

                    # The critical bug pattern is: response appears, then immediately followed
                    # by many \r characters that move the cursor back and overwrite it.
                    # A healthy output might have some \r for prompt management, but not
                    # an excessive amount immediately after the response.
                    #
                    # With sys.stdout.write() fix, the response is written directly without
                    # cursor management, so there should be minimal \r immediately after.
                    #
                    # We look for the pattern: response followed by \r\r\n (CR CR LF)
                    # This indicates the response is being cleared
                    pattern_after_response = after_response[:50]  # First 50 chars after response
                    print(f"[TEST] Pattern after response: {repr(pattern_after_response)}")

                    # Count consecutive CR sequences right after response
                    # The bug pattern is: Hello World\r\r\n\r\r\n\r\r\n... (many CRs)
                    # Fixed pattern is: Hello World\n or Hello World\r\n (single newline)
                    consecutive_cr_pattern = re.search(r'(\r\r?\n)+', pattern_after_response)
                    if consecutive_cr_pattern:
                        cr_sequence_length = len(consecutive_cr_pattern.group(0))
                        print(f"[TEST] CR sequence length after response: {cr_sequence_length}")
                        # More than 6 characters of CR sequences (2x \r\r\n) indicates bug
                        MAX_CR_SEQUENCE = 6
                        assert cr_sequence_length <= MAX_CR_SEQUENCE, (
                            f"BUG DETECTED: Excessive CR sequence ({cr_sequence_length} chars) after response.\n"
                            f"This indicates the response may be getting deleted.\n"
                            f"Pattern: {repr(pattern_after_response)}"
                        )

                print("[TEST] PASS: No excessive carriage returns, response visible")

        except pexpect.TIMEOUT as e:
            print(f"[TEST] Timeout: {e}")
            print(f"[TEST] CLI buffer: {cli_process.before}")
            raise

        finally:
            if cli_process.isalive():
                cli_process.sendline("/exit")
                try:
                    cli_process.expect(pexpect.EOF, timeout=3)
                except:
                    cli_process.terminate()


class TestFlushTokensUnit:
    """
    Unit tests for the flush_tokens function behavior.

    These tests don't require a running server - they test the output
    behavior in isolation.
    """

    @pytest.mark.asyncio
    async def test_token_output_no_carriage_returns(self):
        """
        Test that token output uses sys.stdout.write (not print_formatted_text)
        and doesn't produce carriage returns.

        This is the core unit test for the fix.
        """
        # Import the cli module to test its behavior
        from aigent.interfaces.cli import ws_listener
        from aigent.core.schemas import EventType

        # Create mock websocket that yields TOKEN events
        token_events = [
            {"type": EventType.TOKEN, "content": "Hello"},
            {"type": EventType.TOKEN, "content": " "},
            {"type": EventType.TOKEN, "content": "World"},
            {"type": EventType.FINISH, "content": ""},
        ]

        class MockWebSocket:
            def __init__(self, events):
                self.events = events
                self.index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.events):
                    raise StopAsyncIteration
                event = self.events[self.index]
                self.index += 1
                return json.dumps(event)

        mock_ws = MockWebSocket(token_events)

        # Create mock profile config
        class MockProfileConfig:
            tool_call_preview_length = 100

        profile_config = MockProfileConfig()

        # Create the ready_for_input event
        ready_for_input = asyncio.Event()
        ready_for_input.set()

        # Capture sys.stdout.write calls (tokens now use sys.stdout.write)
        stdout_writes = []

        def capture_write(text):
            stdout_writes.append(text)
            return len(text)

        with patch('sys.stdout.write', side_effect=capture_write):
            with patch('sys.stdout.flush'):
                with patch('prompt_toolkit.print_formatted_text'):
                    # Run the ws_listener
                    await asyncio.wait_for(
                        ws_listener(mock_ws, profile_config, ready_for_input, "test-user"),
                        timeout=5.0
                    )

        # Check what was written
        output = ''.join(stdout_writes)
        print(f"[TEST] Captured stdout writes: {stdout_writes}")
        print(f"[TEST] Full output: {repr(output)}")

        # Check that "Hello World" was output via sys.stdout.write
        assert "Hello" in output, f"'Hello' not in output: {repr(output)}"
        assert "World" in output, f"'World' not in output: {repr(output)}"

        # Check for carriage returns in the output
        # With sys.stdout.write, there should be NO carriage returns
        cr_count = output.count('\r')
        print(f"[TEST] Carriage returns in output: {cr_count}")
        assert cr_count == 0, f"Found {cr_count} carriage returns in output: {repr(output)}"

        print("[TEST] PASS: Token output uses sys.stdout.write with no carriage returns")


# Run with:
# pytest tests/e2e/test_shared_session_bug.py::TestSharedSessionBug -v --run-e2e
# pytest tests/e2e/test_shared_session_bug.py::TestFlushTokensUnit -v --run-e2e

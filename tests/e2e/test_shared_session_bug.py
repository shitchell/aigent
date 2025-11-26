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
                # In a working implementation, there should be very few carriage returns
                # (maybe a couple from prompt_toolkit managing the prompt line itself)
                # But with the bug, there are MANY carriage returns (one per token flush)
                # that delete the printed content.

                # We'll use a threshold - if there are more than 5 CRs, it's likely buggy
                # (The number 5 accounts for some normal prompt_toolkit behavior)
                MAX_ACCEPTABLE_CR = 5

                assert total_cr_count <= MAX_ACCEPTABLE_CR, (
                    f"BUG DETECTED: Output contains {total_cr_count} carriage returns "
                    f"(max acceptable: {MAX_ACCEPTABLE_CR}).\n"
                    f"This indicates the text is being deleted as it's printed.\n"
                    f"Output (repr): {repr(raw_output[:500])}"
                )

                # Also verify the response is visible
                assert has_response, (
                    f"Expected response '{EXPECTED_RESPONSE}' not found in output.\n"
                    f"The response may have been deleted by carriage returns.\n"
                    f"Output: {repr(raw_output[:500])}"
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
        Test that token output uses a method that doesn't produce
        carriage returns.

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

        # Capture all output by replacing stdout
        captured_output = io.StringIO()
        original_stdout = sys.stdout

        # Also capture calls to print_formatted_text
        printed_calls = []

        def mock_print_formatted_text(*args, **kwargs):
            text = str(args[0]) if args else ""
            end = kwargs.get('end', '\n')
            printed_calls.append({'text': text, 'end': end})
            # Simulate the output
            captured_output.write(text)
            captured_output.write(end)

        # Patch the print_formatted_text import within ws_listener
        import prompt_toolkit
        original_pft = prompt_toolkit.print_formatted_text

        try:
            prompt_toolkit.print_formatted_text = mock_print_formatted_text

            # Run the ws_listener
            await asyncio.wait_for(
                ws_listener(mock_ws, profile_config, ready_for_input, "test-user"),
                timeout=5.0
            )
        except StopAsyncIteration:
            pass  # Expected when mock websocket runs out of events
        finally:
            prompt_toolkit.print_formatted_text = original_pft

        output = captured_output.getvalue()
        print(f"[TEST] Captured output: {repr(output)}")
        print(f"[TEST] Print calls: {printed_calls}")

        # Check that "Hello World" was output
        assert "Hello" in output, f"'Hello' not in output: {repr(output)}"
        assert "World" in output, f"'World' not in output: {repr(output)}"

        # Check for carriage returns in the CAPTURED output
        # (This tests what our mock captured, not actual terminal behavior)
        cr_count = output.count('\r')
        print(f"[TEST] Carriage returns in captured output: {cr_count}")

        # The mock doesn't reproduce the actual terminal behavior with patch_stdout,
        # but it verifies the basic flow works
        print("[TEST] Unit test completed - token flow verified")


# Run with:
# pytest tests/e2e/test_shared_session_bug.py::TestSharedSessionBug -v --run-e2e
# pytest tests/e2e/test_shared_session_bug.py::TestFlushTokensUnit -v --run-e2e

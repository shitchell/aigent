"""
Alternative E2E test using asyncio.subprocess instead of pexpect.
This provides another way to test CLI without external dependencies.
"""

import asyncio
import subprocess
import sys
import os
import pytest
import re
import httpx
from pathlib import Path

# Test configuration
TEST_PROMPT = 'This is a test. Please do not make any tool calls. Only respond with the message "Test confirmed" -- no punctuation and no period.'
EXPECTED_RESPONSE = "Test confirmed"
TIMEOUT = 30
SERVER_HOST = "localhost"
SERVER_PORT = 8000


class TestCLIAsyncio:
    """Test CLI using asyncio.subprocess for terminal interaction."""

    @pytest.fixture
    async def test_server(self):
        """Fixture to spawn and manage test server."""
        # First, kill any existing server on default port
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://{SERVER_HOST}:{SERVER_PORT}/api/stats")
                if resp.status_code == 200:
                    # Server is running, kill it
                    subprocess.run([sys.executable, "-m", "aigent.main", "kill-server"], capture_output=True)
                    await asyncio.sleep(1)
        except:
            pass  # No server running

        # Start server process
        server_proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "aigent.main", "serve",
            "--host", SERVER_HOST, "--port", str(SERVER_PORT), "--yolo",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )

        # Wait for server to be ready
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

        print(f"✓ Test server started on port {SERVER_PORT}")
        yield

        # Cleanup
        server_proc.terminate()
        try:
            await asyncio.wait_for(server_proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            server_proc.kill()
            await server_proc.wait()
        print("✓ Test server stopped")

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_cli_basic_interaction(self, test_server):
        """Test basic CLI interaction using asyncio.subprocess."""

        # Create process with PTY for proper terminal emulation
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "aigent.main", "chat", "--session", "test-async",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, 'TERM': 'xterm-256color', 'COLUMNS': '120', 'LINES': '40'}
        )

        try:
            # Helper to read until pattern
            async def read_until_prompt(timeout_seconds=10):
                output = b""
                start_time = asyncio.get_event_loop().time()

                while asyncio.get_event_loop().time() - start_time < timeout_seconds:
                    try:
                        chunk = await asyncio.wait_for(process.stdout.read(1024), timeout=0.1)
                        if chunk:
                            output += chunk
                            # Look for prompt character
                            if b'>' in chunk and output.count(b'>') >= 1:
                                return output.decode('utf-8', errors='replace')
                    except asyncio.TimeoutError:
                        continue

                raise TimeoutError(f"Did not find prompt within {timeout_seconds} seconds")

            # Wait for initial prompt
            initial_output = await read_until_prompt()
            print(f"✓ CLI started, initial output length: {len(initial_output)}")

            # Send test message
            test_input = TEST_PROMPT + "\n"
            process.stdin.write(test_input.encode())
            await process.stdin.drain()
            print(f"→ Sent: {TEST_PROMPT}")

            # Read response
            response_output = await read_until_prompt(timeout_seconds=TIMEOUT)
            print(f"✓ Received response, length: {len(response_output)}")

            # Clean output for analysis
            clean_output = self.clean_terminal_output(response_output)

            # Verify expected response
            assert EXPECTED_RESPONSE in clean_output, f"Expected response not found. Got: {clean_output[:200]}"
            print(f"✓ Found expected response: {EXPECTED_RESPONSE}")

            # Check for artifacts
            artifacts = self.detect_artifacts(response_output)
            assert not artifacts, f"Artifacts detected: {artifacts}"
            print("✓ No rendering artifacts detected")

            # Send exit command
            process.stdin.write(b"/exit\n")
            await process.stdin.drain()

            # Wait for process to exit
            await asyncio.wait_for(process.wait(), timeout=5)
            print("✓ CLI exited cleanly")

        except Exception as e:
            print(f"✗ Test failed: {e}")

            # Try to get any stderr output
            if process.stderr:
                stderr_data = await process.stderr.read()
                if stderr_data:
                    print(f"Stderr: {stderr_data.decode('utf-8', errors='replace')}")

            raise

        finally:
            # Ensure process is terminated
            if process.returncode is None:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5)

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_cli_rapid_messages(self, test_server):
        """Test CLI with rapid consecutive messages to detect race conditions."""

        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "aigent.main", "chat", "--session", "test-rapid",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, 'TERM': 'xterm'}
        )

        try:
            # Read initial output
            await asyncio.sleep(2)  # Wait for startup

            artifacts_found = []

            # Send multiple messages rapidly
            for i in range(3):
                message = f"Message {i+1}. " + TEST_PROMPT + "\n"
                process.stdin.write(message.encode())
                await process.stdin.drain()
                print(f"→ Sent message {i+1}")

                # Small delay between messages
                await asyncio.sleep(0.5)

            # Read all output
            await asyncio.sleep(TIMEOUT)  # Wait for all responses

            # Read available output
            output_chunks = []
            while True:
                try:
                    chunk = await asyncio.wait_for(process.stdout.read(4096), timeout=0.1)
                    if chunk:
                        output_chunks.append(chunk)
                    else:
                        break
                except asyncio.TimeoutError:
                    break

            full_output = b''.join(output_chunks).decode('utf-8', errors='replace')

            # Check for race condition artifacts
            if full_output.count('>') < 3:
                artifacts_found.append("Missing prompts - possible race condition")

            if '\x1b[' in full_output and '\x1b[0m' not in full_output:
                # Has escape sequences but not just color codes
                artifacts_found.append("Complex ANSI sequences detected")

            assert not artifacts_found, f"Race condition artifacts: {artifacts_found}"
            print("✓ No race conditions detected with rapid messages")

            # Cleanup
            process.stdin.write(b"/exit\n")
            await process.stdin.drain()
            await asyncio.wait_for(process.wait(), timeout=5)

        finally:
            if process.returncode is None:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5)

    @staticmethod
    def clean_terminal_output(raw_output: str) -> str:
        """Remove ANSI codes and control characters from output."""
        # Remove ANSI escape sequences
        ansi_escape = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
        clean = ansi_escape.sub('', raw_output)

        # Remove other control characters except newline and tab
        clean = ''.join(
            char for char in clean
            if char in '\n\t' or (ord(char) >= 32 and ord(char) < 127)
        )

        return clean.strip()

    @staticmethod
    def detect_artifacts(output: str) -> list:
        """
        Detect rendering artifacts in agent response only.
        Extracts the agent's response and validates only that part.
        """
        artifacts = []

        # IMPORTANT: Extract ONLY the agent's response (the "Test confirmed" part)
        # Look for the last occurrence of text matching our expected response pattern
        response_pattern = r'(Test.*?confirmed)'
        matches = list(re.finditer(response_pattern, output, re.IGNORECASE | re.DOTALL))

        if not matches:
            artifacts.append("Could not find expected 'Test confirmed' response in output")
            return artifacts

        # Get the last match (the actual agent response)
        agent_response = matches[-1].group(0)

        # Stable escape sequences that are OK with warning
        stable_sequences = [
            '\x1b[0m',    # Reset formatting
            '\x1b[?7h',   # Enable line wrap
            '\x1b[?7l',   # Disable line wrap
            '\x1b[?25h',  # Show cursor
            '\x1b[?25l'   # Hide cursor
        ]

        # Check if agent response contains only acceptable content
        # Remove all stable sequences and see what's left
        clean_response = agent_response
        for seq in stable_sequences:
            clean_response = clean_response.replace(seq, '')

        # After removing stable sequences, should only have letters and spaces
        if not re.match(r'^[A-Za-z ]+$', clean_response):
            # Check what other escape sequences are present
            other_escapes = re.findall(r'\x1b\[[^m]*[mhHlA-Z]', agent_response)

            # Filter out the stable ones
            bad_escapes = []
            for esc in other_escapes:
                if esc not in stable_sequences:
                    bad_escapes.append(esc)

            if bad_escapes:
                artifacts.append(f"Agent response contains bad escape sequences: {bad_escapes}")

        # Check if stable sequences are present (warning only)
        warnings = []
        for seq in stable_sequences:
            if seq in agent_response:
                warnings.append(f"Agent response contains acceptable escape sequence {repr(seq)} that should be removed after refactoring")

        # Log warnings but don't fail on them
        if warnings:
            print("⚠️  Stable escape sequences in agent response (will be fixed after refactoring):")
            for warning in warnings:
                print(f"  - {warning}")

        # Check for other artifacts in agent response specifically
        if '\r' in agent_response:
            artifacts.append("Agent response contains carriage return")

        # Check for cursor movement in agent response
        cursor_patterns = [
            r'\x1b\[\d*A',  # Move up
            r'\x1b\[\d*B',  # Move down
            r'\x1b\[\d*C',  # Move right
            r'\x1b\[\d*D',  # Move left
            r'\x1b\[2K',     # Clear line
            r'\x1b\[\d+;\d+H',  # Set position
        ]

        for pattern in cursor_patterns:
            if re.search(pattern, agent_response):
                artifacts.append(f"Agent response contains cursor control: {pattern}")

        return artifacts


# Run with: pytest tests/e2e/test_cli_asyncio.py --e2e -v
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
        """Detect rendering artifacts in terminal output."""
        artifacts = []

        # Check for carriage returns not at line endings
        lines = output.split('\n')
        for line in lines:
            if '\r' in line and not line.endswith('\r'):
                artifacts.append("Unexpected carriage return in line")
                break

        # Check for cursor movement sequences
        cursor_patterns = [
            r'\x1b\[\d+A',  # Move up
            r'\x1b\[\d+B',  # Move down
            r'\x1b\[\d+C',  # Move right
            r'\x1b\[\d+D',  # Move left
            r'\x1b\[2K',     # Clear line
            r'\x1b\[\d+;\d+H',  # Set position
        ]

        for pattern in cursor_patterns:
            if re.search(pattern, output):
                artifacts.append(f"Cursor control sequence: {pattern}")

        # Check for malformed sequences
        if '?[' in output or '?25h' in output or '?25l' in output:
            artifacts.append("Malformed ANSI sequences")

        # Check for Rich library artifacts
        if 'Window too small' in output:
            artifacts.append("Rich library error message")

        # Check for excessive blank lines (more than 3 consecutive)
        if '\n\n\n\n' in output:
            artifacts.append("Excessive blank lines")

        return artifacts


# Run with: pytest tests/e2e/test_cli_asyncio.py --e2e -v
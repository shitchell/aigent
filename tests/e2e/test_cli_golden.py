"""
Golden file testing for CLI output.
Compares actual CLI output against a known-good reference to detect any changes.
"""

import asyncio
import subprocess
import sys
import os
import pytest
import hashlib
import difflib
import httpx
from pathlib import Path
import pexpect

# Test configuration
TEST_PROMPT = 'This is a test. Please do not make any tool calls. Only respond with the message "Test confirmed" -- no punctuation and no period.'
EXPECTED_RESPONSE = "Test confirmed"
TIMEOUT = 30
SERVER_HOST = "localhost"
SERVER_PORT = 8000

# Path to golden files
GOLDEN_DIR = Path(__file__).parent / "golden_files"
GOLDEN_DIR.mkdir(exist_ok=True)


class TestCLIGolden:
    """Golden file tests for CLI output stability."""

    @pytest.fixture
    async def test_server(self):
        """Fixture to spawn and manage test server."""
        # First, kill any existing server
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://{SERVER_HOST}:{SERVER_PORT}/api/stats")
                if resp.status_code == 200:
                    subprocess.run([sys.executable, "-m", "aigent.main", "kill-server"], capture_output=True)
                    await asyncio.sleep(1)
        except:
            pass

        # Start server process
        server_proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "aigent.main", "serve",
            "--host", SERVER_HOST, "--port", str(SERVER_PORT), "--yolo",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
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
    async def test_cli_golden_output(self, test_server):
        """
        Compare CLI output against a golden reference file.
        This ensures output remains stable across changes.
        """

        golden_file = GOLDEN_DIR / "cli_basic_interaction.txt"
        actual_output = await self.capture_cli_session()

        if not golden_file.exists():
            # First run - create golden file
            print(f"Creating golden file: {golden_file}")
            golden_file.write_text(actual_output)
            pytest.skip("Golden file created. Re-run test to compare.")

        # Load golden reference
        expected_output = golden_file.read_text()

        # Compare outputs
        if actual_output != expected_output:
            # Generate diff for debugging
            diff = difflib.unified_diff(
                expected_output.splitlines(keepends=True),
                actual_output.splitlines(keepends=True),
                fromfile="golden",
                tofile="actual"
            )
            diff_text = ''.join(diff)

            # Save actual output for inspection
            actual_file = GOLDEN_DIR / "cli_basic_interaction_actual.txt"
            actual_file.write_text(actual_output)

            pytest.fail(
                f"CLI output does not match golden file!\n"
                f"Actual output saved to: {actual_file}\n"
                f"Diff:\n{diff_text}"
            )

        print("✓ CLI output matches golden reference")

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_cli_golden_with_artifacts_check(self, test_server):
        """
        Dual test: Compare against golden file AND check for specific artifacts.
        This gives us both regression detection and specific issue detection.
        """

        golden_file = GOLDEN_DIR / "cli_clean_output.txt"
        actual_output = await self.capture_cli_session()

        # Part 1: Artifact detection (handcrafted checks)
        artifacts = self.detect_rendering_artifacts(actual_output)
        assert not artifacts, f"Rendering artifacts detected:\n" + "\n".join(artifacts)
        print("✓ No rendering artifacts detected")

        # Part 2: Golden file comparison
        if golden_file.exists():
            expected_output = golden_file.read_text()

            # Normalize for comparison (remove timestamps, session IDs)
            normalized_actual = self.normalize_output(actual_output)
            normalized_expected = self.normalize_output(expected_output)

            if normalized_actual != normalized_expected:
                # Check if only minor differences
                similarity = self.calculate_similarity(normalized_actual, normalized_expected)
                if similarity < 0.95:  # 95% similarity threshold
                    diff = difflib.unified_diff(
                        normalized_expected.splitlines(keepends=True),
                        normalized_actual.splitlines(keepends=True),
                        fromfile="golden (normalized)",
                        tofile="actual (normalized)"
                    )
                    diff_text = ''.join(list(diff)[:50])  # First 50 lines of diff

                    pytest.fail(
                        f"CLI output significantly differs from golden file!\n"
                        f"Similarity: {similarity:.2%}\n"
                        f"Diff preview:\n{diff_text}"
                    )
                else:
                    print(f"⚠️  Minor differences detected (similarity: {similarity:.2%})")
        else:
            # Create golden file
            golden_file.write_text(actual_output)
            print(f"✓ Golden file created: {golden_file}")

        print("✓ CLI output is clean and stable")

    async def capture_cli_session(self) -> str:
        """Capture a complete CLI session with predictable output."""

        # Use pexpect for accurate terminal capture
        cli_process = pexpect.spawn(
            f"{sys.executable} -m aigent.main chat --session golden-test",
            encoding='utf-8',
            timeout=TIMEOUT,
            env={**os.environ, 'TERM': 'xterm', 'COLUMNS': '80', 'LINES': '24'}
        )

        full_output = []

        try:
            # Wait for initial prompt
            index = cli_process.expect([r'>', pexpect.TIMEOUT], timeout=10)
            full_output.append(cli_process.before)
            full_output.append(cli_process.match.group(0) if cli_process.match else '>')

            # Send test message for predictable response
            cli_process.sendline(TEST_PROMPT)
            full_output.append(TEST_PROMPT + '\n')

            # Wait for response and next prompt
            index = cli_process.expect([r'>', pexpect.TIMEOUT], timeout=TIMEOUT)
            full_output.append(cli_process.before)
            full_output.append(cli_process.match.group(0) if cli_process.match else '>')

            # Exit cleanly
            cli_process.sendline("/exit")
            full_output.append("/exit\n")

            # Wait for EOF
            cli_process.expect(pexpect.EOF, timeout=5)
            if cli_process.before:
                full_output.append(cli_process.before)

        except pexpect.TIMEOUT as e:
            full_output.append(f"\n[TIMEOUT: {e}]")

        finally:
            if cli_process.isalive():
                cli_process.terminate()

        return ''.join(full_output)

    def detect_rendering_artifacts(self, output: str) -> list:
        """
        Detect specific rendering artifacts in agent response only.
        Extracts the agent's response and validates only that part.
        """
        import re

        artifacts = []
        warnings = []

        # IMPORTANT: Extract ONLY the agent's response (the "Test confirmed" part)
        # Look for the last occurrence of text matching our expected response pattern
        response_pattern = r'(Test.*?confirmed)'
        matches = list(re.finditer(response_pattern, output, re.IGNORECASE | re.DOTALL))

        if not matches:
            artifacts.append("Could not find expected 'Test confirmed' response in output")
            return artifacts

        # Get the last match (the actual agent response)
        agent_response = matches[-1].group(0)

        # Now check ONLY the agent response for escape sequences
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
        for seq in stable_sequences:
            if seq in agent_response:
                warnings.append(f"Agent response contains acceptable escape sequence {repr(seq)} that should be removed after refactoring")

        # Check for other artifacts in agent response specifically
        if '\r' in agent_response:
            artifacts.append("Agent response contains carriage return")

        # Check for cursor movement in agent response
        cursor_patterns = [
            (r'\x1b\[\d*A', 'Cursor up'),
            (r'\x1b\[\d*B', 'Cursor down'),
            (r'\x1b\[\d*C', 'Cursor right'),
            (r'\x1b\[\d*D', 'Cursor left'),
            (r'\x1b\[2K', 'Clear line'),
            (r'\x1b\[\d+;\d+H', 'Cursor position'),
        ]

        for pattern, description in cursor_patterns:
            if re.search(pattern, agent_response):
                artifacts.append(f"Agent response contains {description}: {pattern}")

        # Log warnings but don't fail on them
        if warnings:
            print("⚠️  Stable escape sequences in agent response (will be fixed after refactoring):")
            for warning in warnings:
                print(f"  - {warning}")

        return artifacts

    def normalize_output(self, output: str) -> str:
        """
        Normalize output for comparison by removing variable elements.
        This allows golden file comparison even with minor variations.
        """
        import re

        # Remove timestamps
        output = re.sub(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', '[TIMESTAMP]', output)

        # Remove session IDs
        output = re.sub(r'session-[a-f0-9]{8}', 'session-[ID]', output)
        output = re.sub(r'golden-test', 'session-[ID]', output)

        # Remove ANSI color codes (but keep structure)
        output = re.sub(r'\x1b\[[\d;]*m', '', output)

        # Normalize whitespace at line ends
        lines = output.split('\n')
        lines = [line.rstrip() for line in lines]
        output = '\n'.join(lines)

        return output

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity ratio between two texts."""
        matcher = difflib.SequenceMatcher(None, text1, text2)
        return matcher.ratio()


class TestGoldenFileManagement:
    """Utilities for managing golden files."""

    @pytest.mark.e2e
    def test_update_golden_files(self, request):
        """
        Update golden files with current output.
        Run with: pytest tests/e2e/test_cli_golden.py::TestGoldenFileManagement::test_update_golden_files --e2e --update-golden
        """
        if not request.config.getoption("--update-golden", default=False):
            pytest.skip("Use --update-golden flag to update golden files")

        # Capture new golden output
        import asyncio
        test = TestCLIGolden()
        output = asyncio.run(test.capture_cli_session())

        # Update golden files
        golden_file = GOLDEN_DIR / "cli_basic_interaction.txt"
        golden_file.write_text(output)

        # Also create normalized version
        normalized = test.normalize_output(output)
        norm_file = GOLDEN_DIR / "cli_clean_output_normalized.txt"
        norm_file.write_text(normalized)

        print(f"✓ Updated golden files in {GOLDEN_DIR}")

    def test_verify_golden_files(self):
        """Verify golden files exist and are valid."""
        expected_files = [
            "cli_basic_interaction.txt",
            "cli_clean_output.txt"
        ]

        missing = []
        for filename in expected_files:
            if not (GOLDEN_DIR / filename).exists():
                missing.append(filename)

        if missing:
            pytest.skip(f"Golden files missing: {missing}. Run tests to create them.")

        print(f"✓ All golden files present in {GOLDEN_DIR}")


# Add pytest option for updating golden files
def pytest_addoption(parser):
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="Update golden reference files"
    )
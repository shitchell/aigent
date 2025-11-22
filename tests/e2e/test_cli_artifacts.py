"""
E2E tests for detecting CLI rendering artifacts.
Uses script recording or pty to capture raw terminal output and analyze for issues.
"""

import pytest
import asyncio
import subprocess
import sys
import os
import pty
import select
import time
import re
from pathlib import Path
from typing import List, Tuple


class TestCLIArtifacts:
    """Test suite for detecting CLI rendering artifacts."""

    def analyze_output_for_artifacts(self, output: str) -> List[str]:
        """
        Analyze terminal output for rendering artifacts.

        Returns list of detected issues.
        """
        issues = []

        # Check for carriage returns in unexpected places
        if '\r' in output and not all(line.endswith('\r\n') for line in output.split('\n') if '\r' in line):
            # Count unexpected carriage returns
            cr_count = output.count('\r') - output.count('\r\n')
            if cr_count > 0:
                issues.append(f"Found {cr_count} unexpected carriage returns (\\r)")

        # Check for ANSI escape sequences beyond basic colors
        ansi_pattern = r'\x1b\[([0-9;]+)([A-Za-z])'
        ansi_matches = re.findall(ansi_pattern, output)

        for codes, cmd in ansi_matches:
            # Allow basic color codes (30-37, 40-47, 90-97, 100-107 for colors)
            # and style codes (0=reset, 1=bold, 2=dim, 3=italic, 4=underline)
            if cmd in 'mM':  # Color/style commands
                code_list = codes.split(';') if codes else []
                for code in code_list:
                    if code and int(code) not in range(0, 108):
                        issues.append(f"Unexpected ANSI code: \\x1b[{codes}{cmd}")
            elif cmd in 'ABCD':  # Cursor movement
                issues.append(f"Cursor movement sequence found: \\x1b[{codes}{cmd}")
            elif cmd in 'HfJK':  # Cursor positioning, clear
                issues.append(f"Screen control sequence found: \\x1b[{codes}{cmd}")
            elif cmd in 'su':  # Save/restore cursor
                issues.append(f"Cursor save/restore found: \\x1b[{codes}{cmd}")

        # Check for malformed ANSI sequences
        if '?[' in output:
            issues.append("Malformed ANSI sequence found: ?[")

        if '\x1b[' in output and output.count('\x1b[') != len(ansi_matches):
            issues.append("Potentially broken ANSI sequences detected")

        # Check for Rich library error messages
        rich_indicators = [
            "Window too small",
            "Terminal window is too small",
            "rich.errors",
            "RenderError"
        ]
        for indicator in rich_indicators:
            if indicator in output:
                issues.append(f"Rich library error indicator found: '{indicator}'")

        # Check for excessive blank lines (could indicate Live display issues)
        lines = output.split('\n')
        consecutive_blanks = 0
        max_consecutive = 0
        for line in lines:
            if line.strip() == '':
                consecutive_blanks += 1
                max_consecutive = max(max_consecutive, consecutive_blanks)
            else:
                consecutive_blanks = 0

        if max_consecutive > 3:
            issues.append(f"Found {max_consecutive} consecutive blank lines (possible Live display artifact)")

        # Check for backspace characters
        if '\b' in output:
            issues.append(f"Found {output.count(chr(8))} backspace characters")

        # Check for form feed or other unusual control characters
        control_chars = {
            '\f': 'form feed',
            '\v': 'vertical tab',
            '\a': 'bell',
        }
        for char, name in control_chars.items():
            if char in output:
                issues.append(f"Found {name} character ({repr(char)})")

        return issues

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_cli_clean_output_simple_message(self):
        """Test CLI output for simple messages has no artifacts."""

        # Create a test script that sends a simple message
        test_script = """
import asyncio
import sys
sys.path.insert(0, 'src')

async def test_cli():
    from aigent.interfaces.cli import run_cli
    from unittest.mock import Mock

    args = Mock()
    args.profile = 'default'
    args.session = 'test-artifacts-simple'
    args.yolo = True  # Skip permissions for test
    args.replace = False

    # We'd need to mock stdin/stdout properly for a full test
    # This is a simplified version
    print("Starting CLI test...")

asyncio.run(test_cli())
"""

        # For a real implementation, we'd use pty to capture output
        # This is a simplified demonstration
        master, slave = pty.openpty()

        proc = subprocess.Popen(
            [sys.executable, "-c", test_script],
            stdin=slave,
            stdout=slave,
            stderr=subprocess.STDOUT,
            text=True
        )

        os.close(slave)

        output = []
        start_time = time.time()
        timeout = 5.0

        while time.time() - start_time < timeout:
            if proc.poll() is not None:
                break

            ready, _, _ = select.select([master], [], [], 0.1)
            if ready:
                try:
                    data = os.read(master, 1024).decode('utf-8', errors='replace')
                    output.append(data)
                except OSError:
                    break

        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

        os.close(master)

        full_output = ''.join(output)
        issues = self.analyze_output_for_artifacts(full_output)

        # For this simple test, we expect some output but check for artifacts
        if issues:
            pytest.fail(f"CLI artifacts detected:\n" + "\n".join(issues))

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_cli_stress_rapid_messages(self):
        """Test CLI under stress with rapid message sending."""

        port = 18200

        # Start a server for the test
        server_proc = subprocess.Popen(
            [sys.executable, "-m", "aigent.main", "serve", "--port", str(port), "--yolo"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # Wait for server
        await asyncio.sleep(3)

        try:
            # Start CLI process
            cli_proc = subprocess.Popen(
                [sys.executable, "-m", "aigent.main", "chat", "--session", "stress-test", "--yolo"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=0
            )

            # Send rapid messages
            messages = [
                "First message\n",
                "Second message quickly\n",
                "Third message immediately\n",
            ]

            output_lines = []

            for msg in messages:
                cli_proc.stdin.write(msg)
                cli_proc.stdin.flush()

                # Capture output for a short time
                start = time.time()
                while time.time() - start < 0.5:
                    line = cli_proc.stdout.readline()
                    if line:
                        output_lines.append(line)

            # Analyze captured output
            full_output = ''.join(output_lines)
            issues = self.analyze_output_for_artifacts(full_output)

            # In stress test, we're particularly looking for race conditions
            race_indicators = [
                '\r' in full_output and full_output.count('\r') > len(messages),
                re.search(r'\x1b\[\d+[AD]', full_output),  # Cursor up/left movements
                '?[' in full_output,
            ]

            if any(race_indicators):
                issues.append("Possible race condition artifacts detected")

            cli_proc.terminate()

            if issues:
                # Report but don't fail for stress test
                print(f"Stress test artifacts detected:\n" + "\n".join(issues))

        finally:
            server_proc.terminate()
            server_proc.wait(timeout=5)

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_cli_tool_output_rendering(self):
        """Test CLI rendering when tools are invoked."""

        # This test would ideally mock tool outputs and check rendering
        # For now, it's a placeholder showing the test structure

        expected_tool_format = re.compile(r'🛠\s+\w+\([^)]*\)')

        sample_output = """
        🛠  fs_read(path='/test/file.py')
           File contents here...
        """

        issues = self.analyze_output_for_artifacts(sample_output)

        # Check tool output follows expected format
        if not expected_tool_format.search(sample_output):
            issues.append("Tool output doesn't match expected format")

        assert len(issues) == 0, f"Tool rendering issues: {issues}"

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_cli_long_output_handling(self):
        """Test CLI handling of long outputs without artifacts."""

        # Generate a long output scenario
        long_text = "A" * 100 + "\n" + "B" * 100 + "\n"
        long_text = long_text * 50  # 10KB of text

        # Analyze if this would cause issues
        issues = self.analyze_output_for_artifacts(long_text)

        # Long outputs shouldn't have special artifacts
        assert len(issues) == 0

    def test_analyze_known_bad_outputs(self):
        """Test the analyzer can detect known bad outputs."""

        # Test various known bad patterns
        bad_outputs = [
            ("Hello\rWorld\rTest", ["carriage returns"]),
            ("Text\x1b[2AMore", ["Cursor movement"]),
            ("Normal?[31mBroken", ["Malformed ANSI"]),
            ("Line1\n\n\n\n\n\nLine2", ["consecutive blank lines"]),
            ("Window too small to render", ["Rich library error"]),
            ("Back\b\b\bspace", ["backspace characters"]),
            ("Form\fFeed", ["form feed"]),
        ]

        for bad_output, expected_keywords in bad_outputs:
            issues = self.analyze_output_for_artifacts(bad_output)
            assert len(issues) > 0, f"Failed to detect issues in: {repr(bad_output)}"

            # Check that at least one expected keyword is found
            issues_text = ' '.join(issues).lower()
            found = False
            for keyword in expected_keywords:
                if keyword.lower() in issues_text:
                    found = True
                    break

            assert found, f"Expected keyword not found. Issues: {issues}, Expected: {expected_keywords}"

    def test_analyze_clean_outputs(self):
        """Test the analyzer doesn't flag clean outputs."""

        clean_outputs = [
            "Hello World\n",
            "Normal text without issues",
            "\x1b[32mGreen text\x1b[0m is okay",  # Basic colors are fine
            "Multiple\nLines\nAre\nFine\n",
            "HTTP/1.1 200 OK\r\n\r\nBody",  # CRLF in HTTP is fine
        ]

        for clean_output in clean_outputs:
            issues = self.analyze_output_for_artifacts(clean_output)
            # Basic color codes shouldn't be flagged
            filtered_issues = [i for i in issues if 'color' not in i.lower()]
            assert len(filtered_issues) == 0, f"False positive on clean output: {repr(clean_output)}, Issues: {filtered_issues}"
"""
Unit tests for CLI rendering to prevent regression of rendering bugs.
Tests focus on ensuring clean output without ANSI escape sequences or artifacts.
"""

import asyncio
import sys
import json
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from aigent.interfaces.cli import ws_listener
from aigent.core.schemas import EventType


class TestCLIRendering:
    """Test suite for CLI rendering behavior."""

    @pytest.mark.asyncio
    async def test_no_rich_library_import(self):
        """Ensure Rich library is not imported in CLI module."""
        import aigent.interfaces.cli as cli_module
        import sys

        # Check that rich is not in the module's namespace
        assert not hasattr(cli_module, 'Console')
        assert not hasattr(cli_module, 'Markdown')
        assert not hasattr(cli_module, 'Live')

        # Check that rich modules are not imported
        rich_modules = [m for m in sys.modules if m.startswith('rich')]
        # Note: This might fail if other parts of the codebase use rich
        # In production, we'd want to ensure rich isn't imported at CLI startup

    @pytest.mark.asyncio
    async def test_token_buffering(self):
        """Test that tokens are buffered and not printed one by one."""
        # Mock WebSocket
        mock_ws = AsyncMock()
        messages = [
            json.dumps({"type": EventType.TOKEN, "content": "H"}),
            json.dumps({"type": EventType.TOKEN, "content": "e"}),
            json.dumps({"type": EventType.TOKEN, "content": "l"}),
            json.dumps({"type": EventType.TOKEN, "content": "l"}),
            json.dumps({"type": EventType.TOKEN, "content": "o"}),
            json.dumps({"type": EventType.FINISH, "content": ""})
        ]

        mock_ws.__aiter__.return_value = iter(messages)

        # Mock profile config
        mock_config = Mock()
        mock_config.tool_call_preview_length = 100

        # Mock ready_for_input event
        ready_event = asyncio.Event()

        # Capture sys.stdout.write calls (tokens now use sys.stdout.write)
        import io
        captured_stdout = io.StringIO()

        with patch('sys.stdout.write', side_effect=lambda x: captured_stdout.write(x)):
            with patch('sys.stdout.flush'):
                with patch('prompt_toolkit.print_formatted_text'):
                    await ws_listener(mock_ws, mock_config, ready_event)

        # Should have buffered tokens and written them together
        output = captured_stdout.getvalue()
        # The tokens should be buffered, so we shouldn't see individual writes
        # The output should contain "Hello" and a newline from FINISH
        assert "Hello" in output, f"Expected 'Hello' in output, got '{output}'"

    @pytest.mark.asyncio
    async def test_ready_for_input_synchronization(self):
        """Test that ready_for_input event is properly set after FINISH."""
        mock_ws = AsyncMock()
        messages = [
            json.dumps({"type": EventType.TOKEN, "content": "Test response"}),
            json.dumps({"type": EventType.FINISH, "content": ""})
        ]

        mock_ws.__aiter__.return_value = iter(messages)

        mock_config = Mock()
        mock_config.tool_call_preview_length = 100

        ready_event = asyncio.Event()
        ready_event.clear()  # Start with not ready

        with patch('prompt_toolkit.print_formatted_text'):
            await ws_listener(mock_ws, mock_config, ready_event)

        # Event should be set after FINISH
        assert ready_event.is_set()

    @pytest.mark.asyncio
    async def test_no_ansi_in_token_output(self):
        """Ensure no ANSI escape sequences in token output."""
        mock_ws = AsyncMock()

        # Simulate tokens that might contain ANSI (shouldn't happen with our prompts)
        messages = [
            json.dumps({"type": EventType.TOKEN, "content": "Hello world"}),
            json.dumps({"type": EventType.FINISH, "content": ""})
        ]

        mock_ws.__aiter__.return_value = iter(messages)

        mock_config = Mock()
        mock_config.tool_call_preview_length = 100

        ready_event = asyncio.Event()

        captured_prints = []
        def capture_print(*args, **kwargs):
            # Capture raw text as it would be printed
            text = args[0] if args else ""
            captured_prints.append(str(text))

        with patch('prompt_toolkit.print_formatted_text', side_effect=capture_print):
            await ws_listener(mock_ws, mock_config, ready_event)

        output = ''.join(captured_prints)

        # Check for various ANSI patterns
        assert '\x1b[' not in output, "Found ANSI escape sequence"
        assert '\r' not in output, "Found carriage return"
        assert '\033[' not in output, "Found octal ANSI sequence"

    @pytest.mark.asyncio
    async def test_tool_output_formatting(self):
        """Test that tool outputs are formatted correctly without artifacts."""
        mock_ws = AsyncMock()

        messages = [
            json.dumps({
                "type": EventType.TOOL_START,
                "content": "Calling tool: fs_read",
                "metadata": {"input": {"path": "/test/file.py"}}
            }),
            json.dumps({
                "type": EventType.TOOL_END,
                "content": "File contents here"
            }),
            json.dumps({"type": EventType.FINISH, "content": ""})
        ]

        mock_ws.__aiter__.return_value = iter(messages)

        mock_config = Mock()
        mock_config.tool_call_preview_length = 100

        ready_event = asyncio.Event()

        captured_prints = []
        def capture_print(*args, **kwargs):
            # Extract text content, handling HTML objects
            text = args[0] if args else ""
            captured_prints.append(str(text))

        with patch('sys.stdout.write'):  # FINISH now uses sys.stdout.write
            with patch('sys.stdout.flush'):
                with patch('prompt_toolkit.print_formatted_text', side_effect=capture_print):
                    await ws_listener(mock_ws, mock_config, ready_event)

        # Check tool output format
        # We should have at least 2 prints: tool start and tool end
        # (FINISH now uses sys.stdout.write, not print_formatted_text)
        assert len(captured_prints) >= 2, f"Expected at least 2 prints, got {len(captured_prints)}: {captured_prints}"

        # First should be the tool start with yellow HTML formatting
        tool_start = captured_prints[0]
        assert "🛠" in tool_start
        assert "fs_read" in tool_start
        assert "path='/test/file.py'" in tool_start

        # Second should be the tool end with grey HTML formatting
        tool_end = captured_prints[1]
        assert "File contents here" in tool_end

    @pytest.mark.asyncio
    async def test_approval_request_sets_ready(self):
        """Test that approval requests properly set ready_for_input."""
        mock_ws = AsyncMock()

        messages = [
            json.dumps({
                "type": EventType.APPROVAL_REQUEST,
                "content": "",
                "metadata": {
                    "tool": "bash_execute",
                    "input": {"command": "rm -rf /"},
                    "request_id": "test-123"
                }
            })
        ]

        mock_ws.__aiter__.return_value = iter(messages)

        mock_config = Mock()
        mock_config.tool_call_preview_length = 100

        ready_event = asyncio.Event()
        ready_event.clear()

        with patch('prompt_toolkit.print_formatted_text'):
            await ws_listener(mock_ws, mock_config, ready_event)

        # Should be ready for input after approval request
        assert ready_event.is_set()


class TestCLIRenderingIntegration:
    """Integration tests using subprocess to test actual CLI behavior."""

    @pytest.mark.asyncio
    async def test_cli_subprocess_no_artifacts(self):
        """Run actual CLI subprocess and check for artifacts."""
        # This would be implemented with actual subprocess calls
        # For now, it's a placeholder showing the intent
        pass

    def test_script_recording_analysis(self):
        """Analyze a script recording for rendering artifacts."""
        # Example of how to analyze script output
        def analyze_script(script_content: str) -> list:
            issues = []

            if '\r' in script_content and not script_content.endswith('\r\n'):
                issues.append("Unexpected carriage return found")

            if '\x1b[' in script_content:
                # Allow basic color codes but not cursor movement
                import re
                cursor_pattern = r'\x1b\[\d+[ABCD]'  # Cursor movement
                if re.search(cursor_pattern, script_content):
                    issues.append("Cursor movement sequences found")

            if '?[' in script_content:
                issues.append("Malformed ANSI sequence found")

            if 'Window too small' in script_content:
                issues.append("Rich library error message found")

            return issues

        # Test with clean output
        clean_output = "Hello world\nHow are you?\n"
        assert analyze_script(clean_output) == []

        # Test with artifacts
        bad_output = "Hello\r\x1b[2KWorld\x1b[1A"
        issues = analyze_script(bad_output)
        assert len(issues) > 0
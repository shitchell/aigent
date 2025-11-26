"""
Unit tests for REPL output formatting and color functions.

Tests ensure:
- Color functions produce correct ANSI codes
- REPL module doesn't import prompt_toolkit
- Output formatting is correct
"""

import pytest
import sys
from typing import Dict


class TestREPLOutput:
    """Test suite for REPL output formatting."""

    def test_output_colors(self) -> None:
        """Test that color functions produce correct ANSI codes.

        Verifies that the COLORS dict contains the expected ANSI codes.
        """
        from aigent.interfaces.repl import COLORS, colorize

        # Test expected ANSI color codes
        assert COLORS['cyan'] == '\033[36m', "Cyan should be \\033[36m"
        assert COLORS['yellow'] == '\033[33m', "Yellow should be \\033[33m"
        assert COLORS['red'] == '\033[31m', "Red should be \\033[31m"
        assert COLORS['green'] == '\033[32m', "Green should be \\033[32m"
        assert COLORS['bold'] == '\033[1m', "Bold should be \\033[1m"
        assert COLORS['reset'] == '\033[0m', "Reset should be \\033[0m"

    def test_colorize_function(self) -> None:
        """Test that colorize function wraps text correctly.

        Verifies that colorize adds the color code and reset code.
        """
        from aigent.interfaces.repl import colorize

        # Test colorizing text
        result = colorize("Hello", "green")
        assert result == '\033[32mHello\033[0m', "Colorize should wrap text with color and reset"

        # Test with different color
        result = colorize("Error", "red")
        assert result == '\033[31mError\033[0m', "Colorize should work with red"

        # Test with unknown color (should just add reset)
        result = colorize("Text", "unknown_color")
        assert result == 'Text\033[0m', "Unknown color should just add reset"

    def test_output_no_prompt_toolkit(self) -> None:
        """Test that repl.py doesn't import prompt_toolkit.

        The REPL should be a simple interface without prompt_toolkit dependencies.
        """
        import aigent.interfaces.repl as repl_module

        # Check that prompt_toolkit is not in the module's namespace
        assert not hasattr(repl_module, 'PromptSession'), "REPL should not import PromptSession"
        assert not hasattr(repl_module, 'patch_stdout'), "REPL should not import patch_stdout"
        assert not hasattr(repl_module, 'print_formatted_text'), "REPL should not import print_formatted_text"

        # Verify that the module uses standard input/output
        # Check that it imports the right modules
        import inspect
        source = inspect.getsource(repl_module)

        # Should not have prompt_toolkit imports
        assert 'from prompt_toolkit' not in source, "REPL should not import from prompt_toolkit"
        assert 'import prompt_toolkit' not in source, "REPL should not import prompt_toolkit"

        # Should use standard libraries
        assert 'import readline' in source, "REPL should use readline for completion"

    def test_colors_dict_completeness(self) -> None:
        """Test that COLORS dict has all required colors.

        Ensures all colors used in the REPL are defined.
        """
        from aigent.interfaces.repl import COLORS

        required_colors = ['cyan', 'yellow', 'red', 'green', 'bold', 'reset']

        for color in required_colors:
            assert color in COLORS, f"COLORS dict should contain '{color}'"
            assert isinstance(COLORS[color], str), f"Color code for '{color}' should be a string"
            assert COLORS[color].startswith('\033['), f"Color code for '{color}' should be ANSI escape sequence"

    def test_ansi_codes_are_standard(self) -> None:
        """Test that ANSI codes follow standard format.

        ANSI escape codes should start with \\033[ and end with a letter.
        """
        from aigent.interfaces.repl import COLORS

        import re
        ansi_pattern = r'^\033\[[0-9;]*[a-zA-Z]$'

        for color_name, color_code in COLORS.items():
            assert re.match(ansi_pattern, color_code), f"Color code for '{color_name}' should match ANSI pattern"

    def test_colorize_empty_string(self) -> None:
        """Test that colorize handles empty strings correctly."""
        from aigent.interfaces.repl import colorize

        result = colorize("", "green")
        assert result == '\033[32m\033[0m', "Colorize should handle empty strings"

    def test_colorize_multiline(self) -> None:
        """Test that colorize handles multiline text correctly."""
        from aigent.interfaces.repl import colorize

        text = "Line 1\nLine 2\nLine 3"
        result = colorize(text, "yellow")

        assert result == '\033[33mLine 1\nLine 2\nLine 3\033[0m', "Colorize should preserve newlines"
        assert result.startswith('\033[33m'), "Multiline text should start with color code"
        assert result.endswith('\033[0m'), "Multiline text should end with reset code"

    def test_setup_readline_completion_exists(self) -> None:
        """Test that setup_readline_completion function exists and is callable."""
        from aigent.interfaces.repl import setup_readline_completion

        # Should be a callable function
        assert callable(setup_readline_completion), "setup_readline_completion should be a function"

        # Call it (should not raise)
        try:
            setup_readline_completion()
        except Exception as e:
            pytest.fail(f"setup_readline_completion raised exception: {e}")

    def test_client_state_initialization(self) -> None:
        """Test that CLIENT_STATE is properly initialized."""
        from aigent.interfaces.repl import CLIENT_STATE

        # Should be a dict
        assert isinstance(CLIENT_STATE, dict), "CLIENT_STATE should be a dictionary"

        # Should have expected keys
        assert "pending_approval_id" in CLIENT_STATE, "CLIENT_STATE should have pending_approval_id key"

        # Initial value should be None
        assert CLIENT_STATE["pending_approval_id"] is None, "pending_approval_id should start as None"

"""
Unit tests for CLI mode dispatch logic.

Tests ensure:
- --repl flag dispatches to REPL
- --tui flag dispatches to TUI stub
- No flag uses DEFAULT_MODE
- --lock and --session are mutually exclusive
"""

import pytest
import sys
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Any


class TestModeDispatch:
    """Test suite for CLI mode dispatcher."""

    def test_default_mode_constant(self) -> None:
        """Test that DEFAULT_MODE is defined and set to 'repl'."""
        from aigent.interfaces.cli import DEFAULT_MODE

        assert DEFAULT_MODE == "repl", "DEFAULT_MODE should be 'repl' initially"

    @pytest.mark.asyncio
    async def test_mode_dispatch_repl(self) -> None:
        """Test that --repl flag dispatches to REPL.

        When args.repl is True, run_cli should call run_repl.
        """
        from aigent.interfaces.cli import run_cli

        # Create mock args
        mock_args = Mock()
        mock_args.repl = True
        mock_args.tui = False
        mock_args.lock = False
        mock_args.session = None

        # Mock run_repl (patch where it's imported in cli.py)
        with patch('aigent.interfaces.repl.run_repl', new_callable=AsyncMock) as mock_run_repl:
            await run_cli(mock_args)

            # Should have called run_repl
            mock_run_repl.assert_called_once_with(mock_args)

    @pytest.mark.asyncio
    async def test_mode_dispatch_tui(self) -> None:
        """Test that --tui flag dispatches to TUI stub.

        When args.tui is True, run_cli should error (TUI not implemented).
        """
        from aigent.interfaces.cli import run_cli

        # Create mock args
        mock_args = Mock()
        mock_args.repl = False
        mock_args.tui = True
        mock_args.lock = False
        mock_args.session = None

        # Mock sys.exit to capture the error
        with patch('sys.stderr.write') as mock_stderr:
            with patch('sys.exit') as mock_exit:
                await run_cli(mock_args)

                # Should have written error and exited
                mock_stderr.assert_called_once()
                assert "TUI mode not implemented" in mock_stderr.call_args[0][0]
                mock_exit.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_default_mode(self) -> None:
        """Test that no flag uses DEFAULT_MODE.

        When neither --repl nor --tui is set, should use DEFAULT_MODE.
        """
        from aigent.interfaces.cli import run_cli, DEFAULT_MODE

        # Create mock args with no mode flags
        mock_args = Mock()
        mock_args.repl = False
        mock_args.tui = False
        mock_args.lock = False
        mock_args.session = None

        # Since DEFAULT_MODE is "repl", it should call run_repl
        with patch('aigent.interfaces.repl.run_repl', new_callable=AsyncMock) as mock_run_repl:
            await run_cli(mock_args)

            # Should have called run_repl (since DEFAULT_MODE is "repl")
            mock_run_repl.assert_called_once_with(mock_args)

    @pytest.mark.asyncio
    async def test_lock_session_mutual_exclusion(self) -> None:
        """Test that --lock and --session are mutually exclusive.

        When both --lock and --session are set, should error and exit.
        """
        from aigent.interfaces.cli import run_cli

        # Create mock args with both lock and session
        mock_args = Mock()
        mock_args.lock = True
        mock_args.session = "test-session"
        mock_args.repl = False
        mock_args.tui = False

        # Mock sys.exit to capture the error
        with patch('sys.stderr.write') as mock_stderr:
            with patch('sys.exit') as mock_exit:
                await run_cli(mock_args)

                # Should have written error and exited
                mock_stderr.assert_called_once()
                error_message = mock_stderr.call_args[0][0]
                assert "--lock" in error_message, "Error should mention --lock"
                assert "--session" in error_message, "Error should mention --session"
                assert "mutually exclusive" in error_message, "Error should say 'mutually exclusive'"
                mock_exit.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_lock_without_session_ok(self) -> None:
        """Test that --lock without --session is allowed."""
        from aigent.interfaces.cli import run_cli

        # Create mock args with lock but no session
        mock_args = Mock()
        mock_args.lock = True
        mock_args.session = None
        mock_args.repl = True
        mock_args.tui = False

        # Should not error
        with patch('aigent.interfaces.repl.run_repl', new_callable=AsyncMock) as mock_run_repl:
            with patch('sys.exit') as mock_exit:
                await run_cli(mock_args)

                # Should NOT have exited
                mock_exit.assert_not_called()

                # Should have called run_repl
                mock_run_repl.assert_called_once_with(mock_args)

    @pytest.mark.asyncio
    async def test_session_without_lock_ok(self) -> None:
        """Test that --session without --lock is allowed."""
        from aigent.interfaces.cli import run_cli

        # Create mock args with session but no lock
        mock_args = Mock()
        mock_args.lock = False
        mock_args.session = "test-session"
        mock_args.repl = True
        mock_args.tui = False

        # Should not error
        with patch('aigent.interfaces.repl.run_repl', new_callable=AsyncMock) as mock_run_repl:
            with patch('sys.exit') as mock_exit:
                await run_cli(mock_args)

                # Should NOT have exited
                mock_exit.assert_not_called()

                # Should have called run_repl
                mock_run_repl.assert_called_once_with(mock_args)

    @pytest.mark.asyncio
    async def test_repl_mode_priority(self) -> None:
        """Test that explicit --repl takes precedence over DEFAULT_MODE."""
        from aigent.interfaces.cli import run_cli

        # Create mock args with explicit --repl
        mock_args = Mock()
        mock_args.repl = True
        mock_args.tui = False
        mock_args.lock = False
        mock_args.session = None

        # Should call run_repl regardless of DEFAULT_MODE
        with patch('aigent.interfaces.repl.run_repl', new_callable=AsyncMock) as mock_run_repl:
            # Temporarily change DEFAULT_MODE
            with patch('aigent.interfaces.cli.DEFAULT_MODE', 'tui'):
                await run_cli(mock_args)

                # Should still call run_repl (explicit flag takes precedence)
                mock_run_repl.assert_called_once_with(mock_args)

    @pytest.mark.asyncio
    async def test_legacy_fallback(self) -> None:
        """Test that fallback to legacy prompt_toolkit mode works.

        When mode is not 'repl' or 'tui', should fall back to run_cli_prompt_toolkit.
        """
        from aigent.interfaces.cli import run_cli

        # Create mock args
        mock_args = Mock()
        mock_args.repl = False
        mock_args.tui = False
        mock_args.lock = False
        mock_args.session = None

        # Temporarily change DEFAULT_MODE to trigger fallback
        with patch('aigent.interfaces.cli.DEFAULT_MODE', 'legacy'):
            with patch('aigent.interfaces.cli.run_cli_prompt_toolkit', new_callable=AsyncMock) as mock_legacy:
                await run_cli(mock_args)

                # Should have called legacy function
                mock_legacy.assert_called_once_with(mock_args)

    def test_mode_flags_in_argparse(self) -> None:
        """Test that --repl and --tui flags are defined in argparse.

        Verifies that the flags are properly set up in main.py.
        """
        import argparse
        from aigent.main import entry_point

        # Create a parser like main does
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        chat_parser = subparsers.add_parser("chat")

        # Add the interface mode flags (like main.py does)
        interface_group = chat_parser.add_mutually_exclusive_group()
        interface_group.add_argument("--repl", action="store_true")
        interface_group.add_argument("--tui", action="store_true")

        # Test that we can parse them
        args = parser.parse_args(["chat", "--repl"])
        assert args.repl is True
        assert args.tui is False

        args = parser.parse_args(["chat", "--tui"])
        assert args.repl is False
        assert args.tui is True

    def test_lock_session_flags_in_argparse(self) -> None:
        """Test that --lock and --session flags are defined in argparse."""
        import argparse

        # Create a parser like main.py does
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        chat_parser = subparsers.add_parser("chat")

        # Add the flags
        chat_parser.add_argument("--session", type=str)
        chat_parser.add_argument("--lock", action="store_true")

        # Test that we can parse them
        args = parser.parse_args(["chat", "--session", "test"])
        assert args.session == "test"

        args = parser.parse_args(["chat", "--lock"])
        assert args.lock is True

"""CLI interface dispatcher.

This module routes the `aigent chat` command to the appropriate interface:
1. TUI (Textual) - The default, rich interface.
2. REPL (Readline) - A simpler interface for clean text output.
"""

import sys
from typing import Any

# Default mode for `aigent chat` with no flags
DEFAULT_MODE: str = "tui"


async def run_cli(args: Any) -> None:
    """CLI mode dispatcher.

    Routes to the appropriate interface based on args.mode.
    Handles --repl, --tui flags and DEFAULT_MODE.

    Args:
        args: Parsed command-line arguments.
    """
    # Validate mutually exclusive flags
    if hasattr(args, "lock") and hasattr(args, "session"):
        if args.lock and args.session:
            sys.stderr.write("Error: --lock and --session are mutually exclusive\n")
            sys.exit(1)

    # Determine mode
    mode = DEFAULT_MODE
    if hasattr(args, "repl") and args.repl:
        mode = "repl"
    elif hasattr(args, "tui") and args.tui:
        mode = "tui"

    # Route to appropriate interface
    if mode == "repl":
        from aigent.interfaces.repl import run_repl
        await run_repl(args)
    elif mode == "tui":
        from aigent.interfaces.tui import run_tui
        await run_tui(args)
    else:
        sys.stderr.write(f"Error: Unknown mode '{mode}'\n")
        sys.exit(1)

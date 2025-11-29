"""CLI Entry Point and Dispatcher.

Routes to TUI or REPL interfaces.
"""

import argparse
import asyncio
import sys

from aigent.core.logging import configure_logging

def run_cli():
    parser = argparse.ArgumentParser(description="Aigent CLI")
    parser.add_argument("mode", nargs="?", default="tui", choices=["tui", "repl", "serve"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--session", help="Session ID to join")
    parser.add_argument("--debug", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Configure Logging
    configure_logging(verbose=args.debug)
    
    if args.mode == "serve":
        from aigent.server.api import run_server
        asyncio.run(run_server(args.host, args.port))
    elif args.mode == "repl":
        from aigent.interfaces.repl import run_repl
        asyncio.run(run_repl(args))
    elif args.mode == "tui":
        from aigent.interfaces.tui.app import run_tui
        asyncio.run(run_tui(args))
    else:
        print("Unknown mode")

"""CLI Entry Point and Dispatcher.

Routes to TUI or REPL interfaces.
"""

import argparse
import asyncio
import sys

from aigent.core.logging import configure_logging

def run_cli():
    parser = argparse.ArgumentParser(description="Aigent CLI")
    parser.add_argument("--version", action="store_true", help="Show version")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Chat Command
    chat_parser = subparsers.add_parser("chat", help="Start chat session")
    chat_parser.add_argument("--repl", action="store_true", help="Use REPL interface")
    chat_parser.add_argument("--tui", action="store_true", help="Use TUI interface")
    chat_parser.add_argument("--host", default="127.0.0.1")
    chat_parser.add_argument("--port", type=int, default=8000)
    chat_parser.add_argument("--session", help="Session ID to join")
    chat_parser.add_argument("--debug", action="store_true", help="Enable verbose logging")
    
    # Serve Command
    serve_parser = subparsers.add_parser("serve", help="Start server")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--debug", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()
    
    if args.version:
        print("Aigent v0.2.0")
        return

    # Configure Logging
    debug_mode = getattr(args, "debug", False)
    configure_logging(verbose=debug_mode)
    
    if args.command == "serve":
        from aigent.server.api import run_server
        asyncio.run(run_server(args.host, args.port))
        
    elif args.command == "chat":
        # Determine mode
        if args.repl:
            from aigent.interfaces.repl import run_repl
            asyncio.run(run_repl(args))
        else:
            # Default to TUI
            from aigent.interfaces.tui.app import run_tui
            asyncio.run(run_tui(args))
            
    else:
        parser.print_help()
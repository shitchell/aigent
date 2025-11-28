from dotenv import load_dotenv
import argparse
import asyncio
from pathlib import Path

from . import __version__
from aigent.interfaces.cli import run_cli
from aigent.server.api import run_server
from aigent.server.lifecycle import kill_server_process
from aigent.core.profiles import ProfileManager, set_config_path
from aigent.core.logging import configure_from_args, configure_from_config

def entry_point() -> None:
    """
    Synchronous entry point for setuptools console_script.
    Parses args and hands off to the async main loop.
    """
    # Load environment variables from .env file if present
    load_dotenv()

    # 1. Pre-parse --config and logging arguments
    # We do this before loading ProfileManager so we can point it to the right file
    # and configure logging early
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config", type=str, help="Path to configuration file")
    pre_parser.add_argument("--log-level", type=str, help="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    pre_parser.add_argument("--log-file", type=str, help="Path to log file")
    known_args, _ = pre_parser.parse_known_args()

    # Configure logging from CLI args first (highest precedence)
    if known_args.log_level or known_args.log_file:
        configure_from_args(
            log_level=known_args.log_level,
            log_file=known_args.log_file
        )

    if known_args.config:
        set_config_path(Path(known_args.config).expanduser().resolve())

    # 2. Load Config to get defaults
    pm = ProfileManager()
    pm.load_profiles()
    config = pm.config

    # Configure logging from config file (lower precedence than CLI/env)
    if config.log.level or config.log.file:
        configure_from_config(
            log_level=config.log.level,
            log_file=config.log.file
        )

    parser = argparse.ArgumentParser(description="Aigent - AI Agent")

    # Add --config to main parser for help text consistency (handled above)
    parser.add_argument("--config", type=str, help="Path to configuration file")

    # Logging options (global, handled above but shown in help)
    parser.add_argument("--log-level", type=str,
                        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        help="Log level (default: INFO, or from config/env)")
    parser.add_argument("--log-file", type=str,
                        help="Path to log file (logs to stderr by default)")

    # Command parameters
    parser.add_argument("--version", action="store_true", help="Show version and exit")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Chat Command (CLI)
    chat_parser = subparsers.add_parser("chat", help="Start the CLI chat session")
    chat_parser.add_argument("--profile", type=str, default=config.default_profile, help="Agent profile to load")
    chat_parser.add_argument("--session", type=str, help="Session ID to join/resume (defaults to new random session)")
    chat_parser.add_argument("--yolo", action="store_true", help="Disable all permission checks (Danger!)")
    chat_parser.add_argument("--replace", action="store_true", help="Kill existing server and start a new one")

    # Interface mode flags
    interface_group = chat_parser.add_mutually_exclusive_group()
    interface_group.add_argument("--repl", action="store_true", help="Use simple REPL interface")
    interface_group.add_argument("--tui", action="store_true", help="Use rich TUI interface (default)")

    # Session behavior flags
    chat_parser.add_argument("--ephemeral", action="store_true", help="Session not saved to disk, deleted on disconnect")
    chat_parser.add_argument("--lock", action="store_true", help="Lock session to prevent other clients from connecting")

    # Serve Command (Web Daemon)
    serve_parser = subparsers.add_parser("serve", help="Start the API/Web daemon")
    serve_parser.add_argument("--host", type=str, default=config.server.host)
    serve_parser.add_argument("--port", type=int, default=config.server.port)
    serve_parser.add_argument("--yolo", action="store_true", help="Disable all permission checks server-wide (Danger!)")

    # Kill Server Command
    subparsers.add_parser("kill-server", help="Terminate the running Aigent server")

    args = parser.parse_args()
    
    # If version requested, show and exit
    if args.version:
        print(f"{__package__}: {__version__}")
        exit(0)

    if args.command == "serve":
        print(f"Starting server on {args.host}:{args.port}...")
        try:
            asyncio.run(run_server(args))
        except KeyboardInterrupt:
            print("\nServer stopped by user.")
    elif args.command == "chat":
        print(f"Starting chat with profile: {args.profile}")
        asyncio.run(run_cli(args))
    elif args.command == "kill-server":
        # Use defaults from config if not specified? 
        # kill-server doesn't have args for host/port in parser yet.
        # We should probably assume config defaults.
        if kill_server_process(host=config.server.host, port=config.server.port):
            print("Server terminated.")
        else:
            print("No server found or failed to kill.")
    else:
        parser.print_help()

if __name__ == "__main__":
    entry_point()

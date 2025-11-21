from dotenv import load_dotenv
import argparse
import asyncio
from pathlib import Path

from aigent.interfaces.cli import run_cli
from aigent.server.api import run_server
from aigent.server.lifecycle import kill_server_process
from aigent.core.profiles import ProfileManager, set_config_path

def entry_point() -> None:
    """
    Synchronous entry point for setuptools console_script.
    Parses args and hands off to the async main loop.
    """
    # Load environment variables from .env file if present
    load_dotenv()
    
    # 1. Pre-parse --config argument
    # We do this before loading ProfileManager so we can point it to the right file
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config", type=str, help="Path to configuration file")
    known_args, _ = pre_parser.parse_known_args()
    
    if known_args.config:
        set_config_path(Path(known_args.config).expanduser().resolve())
    
    # 2. Load Config to get defaults
    pm = ProfileManager()
    pm.load_profiles()
    config = pm.config

    parser = argparse.ArgumentParser(description="Aigent - AI Agent")
    
    # Add --config to main parser for help text consistency (handled above)
    parser.add_argument("--config", type=str, help="Path to configuration file")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Chat Command (CLI)
    chat_parser = subparsers.add_parser("chat", help="Start the CLI chat session")
    chat_parser.add_argument("--profile", type=str, default=config.default_profile, help="Agent profile to load")
    chat_parser.add_argument("--session", type=str, help="Session ID to join/resume (defaults to new random session)")
    chat_parser.add_argument("--yolo", action="store_true", help="Disable all permission checks (Danger!)")
    chat_parser.add_argument("--replace", action="store_true", help="Kill existing server and start a new one")

    # Serve Command (Web Daemon)
    serve_parser = subparsers.add_parser("serve", help="Start the API/Web daemon")
    serve_parser.add_argument("--host", type=str, default=config.server.host)
    serve_parser.add_argument("--port", type=int, default=config.server.port)
    serve_parser.add_argument("--yolo", action="store_true", help="Disable all permission checks server-wide (Danger!)")

    # Kill Server Command
    subparsers.add_parser("kill-server", help="Terminate the running Aigent server")

    args = parser.parse_args()

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
        if kill_server_process():
            print("Server terminated.")
        else:
            print("No server found or failed to kill.")
    else:
        parser.print_help()

if __name__ == "__main__":
    entry_point()

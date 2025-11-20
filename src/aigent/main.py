import argparse
import asyncio
import sys
from typing import Optional, NoReturn
from dotenv import load_dotenv

# We will import the actual interfaces here later
from aigent.interfaces.cli import run_cli
from aigent.server.api import run_server
from aigent.core.profiles import ProfileManager

def entry_point() -> None:
    """
    Synchronous entry point for setuptools console_script.
    Parses args and hands off to the async main loop.
    """
    # Load environment variables from .env file if present
    load_dotenv()
    
    # Load Config to get defaults
    pm = ProfileManager()
    pm.load_profiles()
    config = pm.config

    parser = argparse.ArgumentParser(description="Aigent - AI Agent")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Chat Command (CLI)
    chat_parser = subparsers.add_parser("chat", help="Start the CLI chat session")
    chat_parser.add_argument("--profile", type=str, default=config.default_profile, help="Agent profile to load")
    chat_parser.add_argument("--yolo", action="store_true", help="Disable all permission checks (Danger!)")

    # Serve Command (Web Daemon)
    serve_parser = subparsers.add_parser("serve", help="Start the API/Web daemon")
    serve_parser.add_argument("--host", type=str, default=config.server_host)
    serve_parser.add_argument("--port", type=int, default=config.server_port)
    serve_parser.add_argument("--yolo", action="store_true", help="Disable all permission checks server-wide (Danger!)")

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
    else:
        parser.print_help()

if __name__ == "__main__":
    entry_point()

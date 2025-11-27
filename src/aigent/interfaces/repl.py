"""Simple REPL interface for Aigent.

This module implements a basic read-eval-print loop using standard input/output
with minimal ANSI coloring. It connects to the WebSocket server for agent
communication and provides slash command completion via readline.

The REPL is designed to be simple and predictable - no cursor manipulation,
no complex rendering. Just clean text output.
"""

import asyncio
import json
import readline
import sys
import uuid
from typing import Optional, Any, Dict

import httpx
import websockets
from subprocess import Popen, DEVNULL

from aigent.core.profiles import ProfileManager
from aigent.core.schemas import EventType
from aigent.interfaces.commands import get_command_names, handle_command, CommandContext


# ANSI color codes for terminal output
COLORS: Dict[str, str] = {
    'cyan': '\033[36m',
    'yellow': '\033[33m',
    'red': '\033[31m',
    'green': '\033[32m',
    'bold': '\033[1m',
    'reset': '\033[0m',
}


# Shared state for approval handling
CLIENT_STATE: Dict[str, Any] = {
    "pending_approval_id": None,
}


def colorize(text: str, color: str) -> str:
    """Apply ANSI color to text.

    Args:
        text: The text to colorize.
        color: Color name from COLORS dict.

    Returns:
        Text wrapped with ANSI color codes.
    """
    return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"


def setup_readline_completion() -> None:
    """Configure readline for slash command completion.

    Sets up tab completion for slash commands using the command registry.
    """
    # Get all slash commands
    commands = get_command_names()

    def completer(text: str, state: int) -> Optional[str]:
        """Readline completer function for slash commands.

        Args:
            text: Current text being completed.
            state: Completion state (0 for first match, 1 for second, etc).

        Returns:
            Next matching command or None when exhausted.
        """
        # Only complete if we're at the start and text begins with /
        line = readline.get_line_buffer()
        if not line.startswith('/'):
            return None

        # Get matching commands
        matches = [cmd for cmd in commands if cmd.startswith(text)]

        if state < len(matches):
            return matches[state]
        return None

    # Configure readline
    readline.parse_and_bind("tab: complete")
    readline.set_completer(completer)


async def check_server(url: str) -> bool:
    """Check if the server is running.

    Args:
        url: Base URL of the server to check.

    Returns:
        True if server is responding, False otherwise.
    """
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url)
            return resp.status_code == 200
        except Exception:
            return False


def start_server(host: str, port: int, yolo: bool) -> None:
    """Start the Aigent server in the background.

    Args:
        host: Host address to bind server to.
        port: Port number to bind server to.
        yolo: Whether to disable all permission checks.
    """
    sys.__stdout__.write(colorize("Starting background server...\n", "green"))
    sys.__stdout__.flush()

    cmd = [sys.executable, "-m", "aigent.main", "serve", "--host", host, "--port", str(port)]
    if yolo:
        cmd.append("--yolo")
    Popen(cmd, stdout=DEVNULL, stderr=DEVNULL, start_new_session=True)


async def ws_listener(
    ws: Any,
    profile_config: Any,
    ready_for_input: asyncio.Event,
    this_user_id: str
) -> None:
    """Listen for WebSocket events and display them.

    This coroutine runs in the background, receiving events from the server
    and printing them to stdout with appropriate formatting.

    Args:
        ws: WebSocket connection.
        profile_config: Profile configuration object.
        ready_for_input: Event to signal when prompt should be shown.
        this_user_id: Unique ID for this client instance.
    """
    token_buffer: list[str] = []
    last_flush_time = asyncio.get_event_loop().time()
    FLUSH_INTERVAL = 0.1  # Flush every 100ms

    async def flush_tokens() -> None:
        """Flush buffered tokens to stdout."""
        nonlocal token_buffer
        if token_buffer:
            sys.__stdout__.write(''.join(token_buffer))
            sys.__stdout__.flush()
            token_buffer = []

    try:
        async for message in ws:
            data = json.loads(message)
            event_type = data.get("type")
            content = data.get("content", "")
            metadata = data.get("metadata", {})

            if event_type == EventType.TOKEN:
                # Buffer tokens to reduce output calls
                token_buffer.append(content)

                # Flush if enough time has passed or buffer is large
                current_time = asyncio.get_event_loop().time()
                if (current_time - last_flush_time > FLUSH_INTERVAL or
                    len(''.join(token_buffer)) > 100):
                    await flush_tokens()
                    last_flush_time = current_time

            else:
                # Flush remaining tokens before handling other events
                await flush_tokens()

                if event_type == EventType.TOOL_START:
                    input_args = metadata.get("input", {})
                    formatted_args = ", ".join([f"{k}={repr(v)}" for k, v in input_args.items()])
                    limit = profile_config.tool_call_preview_length
                    if len(formatted_args) > limit:
                        formatted_args = formatted_args[:limit] + "..."
                    tool_name = content.replace("Calling tool: ", "")
                    sys.__stdout__.write(colorize(f"🛠  {tool_name}({formatted_args})\n", "yellow"))
                    sys.__stdout__.flush()

                elif event_type == EventType.TOOL_END:
                    if len(content) > 500:
                        content = content[:500] + "..."
                    sys.__stdout__.write(f"   {content}\n")
                    sys.__stdout__.flush()

                elif event_type == EventType.USER_INPUT:
                    # Another client sent a message
                    sender_id = metadata.get("user_id", "unknown")
                    if sender_id != this_user_id:
                        ready_for_input.clear()
                        sys.__stdout__.write(colorize(f"[{sender_id}] ", "cyan") + content + "\n")
                        sys.__stdout__.flush()

                elif event_type == EventType.ERROR:
                    sys.__stdout__.write(colorize(f"Error: {content}\n", "red"))
                    sys.__stdout__.flush()
                    ready_for_input.set()

                elif event_type == EventType.SYSTEM:
                    sys.__stdout__.write(colorize(f"System: {content}\n", "green"))
                    sys.__stdout__.flush()

                elif event_type == EventType.HISTORY_CONTENT:
                    sys.__stdout__.write(content + "\n")
                    sys.__stdout__.flush()

                elif event_type == EventType.FINISH:
                    # End of turn - ensure all output is complete before showing prompt
                    await flush_tokens()
                    sys.__stdout__.write("\n")
                    sys.__stdout__.flush()
                    # Small delay to ensure OS has processed all output
                    # This prevents race conditions where prompt appears before tool output
                    await asyncio.sleep(0.01)
                    ready_for_input.set()

                elif event_type == EventType.APPROVAL_REQUEST:
                    tool = metadata.get("tool")
                    args = metadata.get("input")
                    req_id = metadata.get("request_id")

                    CLIENT_STATE["pending_approval_id"] = req_id

                    sys.__stdout__.write(colorize(f"✋ Permission Request: {tool}\n", "yellow"))
                    sys.__stdout__.write(f"   Args: {args}\n")
                    sys.__stdout__.write(colorize("   Allow? [y/n/a(lways tool)/s(smart)]\n", "yellow"))
                    sys.__stdout__.flush()
                    ready_for_input.set()

    except websockets.ConnectionClosed:
        await flush_tokens()
        sys.__stdout__.write(colorize("Connection to server lost.\n", "red"))
        sys.__stdout__.flush()


async def get_input_async(prompt: str) -> str:
    """Get user input asynchronously.

    Uses asyncio.to_thread to avoid blocking the event loop.

    Args:
        prompt: Prompt text to display.

    Returns:
        User input string.

    Raises:
        EOFError: If EOF is encountered.
        KeyboardInterrupt: If user interrupts with Ctrl+C.
    """
    return await asyncio.to_thread(input, prompt)


async def run_repl(args: Any) -> None:
    """Run the REPL interface.

    This is the main entry point for REPL mode. It:
    1. Connects to or starts the server
    2. Sets up readline completion
    3. Runs the input loop
    4. Handles WebSocket communication

    Args:
        args: Parsed command-line arguments.
    """
    # Setup readline completion
    setup_readline_completion()

    # Load configuration
    pm = ProfileManager()
    config = pm.config

    host = config.server.host
    port = config.server.port
    base_url = f"http://{host}:{port}"

    # Determine session ID
    should_lock = False
    show_warning = False

    if hasattr(args, "session") and args.session:
        session_id = args.session
        show_warning = True  # Warn about shared session mode
    else:
        session_id = f"cli-{uuid.uuid4().hex[:8]}"
        should_lock = True  # Lock new sessions by default in REPL

    # Check for explicit --lock flag (for TUI compatibility)
    if hasattr(args, "lock") and args.lock:
        should_lock = True
        show_warning = False  # No warning if explicitly locked

    # Generate unique user ID
    user_id = f"cli-{uuid.uuid4().hex[:8]}"
    ws_url = f"ws://{host}:{port}/ws/chat/{session_id}?profile={args.profile}&user_id={user_id}"

    # Check if we need to replace existing server
    if hasattr(args, "replace") and args.replace:
        from aigent.server.lifecycle import kill_server_process
        sys.__stdout__.write(colorize("Replacing existing server...\n", "yellow"))
        sys.__stdout__.flush()
        kill_server_process(host=host, port=port)
        await asyncio.sleep(1)

    # Auto-start server if not running
    if not await check_server(base_url):
        start_server(host, port, args.yolo)
        # Wait for server to start
        for _ in range(10):
            await asyncio.sleep(1)
            if await check_server(base_url):
                break
        else:
            sys.__stdout__.write(colorize("Failed to start server.\n", "red"))
            sys.__stdout__.flush()
            return

    # Connect and run
    ready_for_input = asyncio.Event()
    ready_for_input.set()

    try:
        async with websockets.connect(ws_url) as ws:
            sys.__stdout__.write(colorize("Connected to Aigent Server.\n", "green"))
            sys.__stdout__.flush()

            # Send lock request if needed
            if should_lock:
                lock_msg = json.dumps({"type": "lock_session"})
                await ws.send(lock_msg)

            # Send ephemeral flag if set
            if hasattr(args, "ephemeral") and args.ephemeral:
                ephemeral_msg = json.dumps({"type": "set_ephemeral", "ephemeral": True})
                await ws.send(ephemeral_msg)

            # Show warning for shared session mode
            if show_warning:
                sys.__stdout__.write(colorize(
                    "Warning: Shared session mode - incoming messages from other clients may cause display issues.\n",
                    "yellow"
                ))
                sys.__stdout__.flush()

            # Start background listener
            listener = asyncio.create_task(
                ws_listener(ws, config, ready_for_input, user_id)
            )

            # Create command context
            cmd_context = CommandContext(websocket=ws)

            try:
                while True:
                    # Check if listener died
                    if listener.done():
                        break

                    # Wait until ready for input
                    await ready_for_input.wait()

                    # Show prompt
                    if CLIENT_STATE["pending_approval_id"]:
                        prompt_text = colorize("Decision > ", "yellow") + colorize("", "bold")
                    else:
                        prompt_text = colorize("> ", "bold")

                    try:
                        user_input = await get_input_async(prompt_text)
                    except (EOFError, KeyboardInterrupt):
                        sys.__stdout__.write("\n")
                        sys.__stdout__.flush()
                        break

                    if not user_input.strip():
                        continue

                    # Handle approval response
                    if CLIENT_STATE["pending_approval_id"]:
                        ans = user_input.lower().strip()
                        decision = "deny"
                        if ans in ['y', 'yes']:
                            decision = "allow"
                        elif ans in ['n', 'no']:
                            decision = "deny"
                        elif ans in ['a', 'always']:
                            decision = "always_tool"
                        elif ans in ['s', 'smart']:
                            decision = "always_smart"

                        msg = {
                            "type": "approval_response",
                            "request_id": CLIENT_STATE["pending_approval_id"],
                            "decision": decision
                        }
                        await ws.send(json.dumps(msg))
                        CLIENT_STATE["pending_approval_id"] = None
                        # Clear ready_for_input to wait for tool execution to complete
                        ready_for_input.clear()
                        continue

                    # Handle slash commands
                    if user_input.strip().startswith("/"):
                        if await handle_command(user_input, cmd_context):
                            if cmd_context.should_exit:
                                break
                            continue

                    # Send message to agent
                    ready_for_input.clear()
                    await ws.send(user_input)

            finally:
                listener.cancel()
                try:
                    await listener
                except asyncio.CancelledError:
                    pass

    except Exception as e:
        sys.__stdout__.write(colorize(f"Error: {e}\n", "red"))
        sys.__stdout__.flush()

"""CLI interface dispatcher and legacy prompt_toolkit implementation.

This module contains:
1. Mode dispatcher for REPL vs TUI
2. Legacy prompt_toolkit-based CLI (run_cli_prompt_toolkit)

The dispatcher allows easy switching between interface modes.
"""

import asyncio
import sys
import json
import httpx
import websockets
from subprocess import Popen, DEVNULL
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.completion import WordCompleter
from typing import Any

from aigent.core.profiles import ProfileManager
from aigent.core.schemas import EventType
from aigent.interfaces.commands import get_command_names, handle_command, CommandContext
from aigent.server.lifecycle import kill_server_process

# Default mode for `aigent chat` with no flags
# Change this to "tui" once TUI is vetted
DEFAULT_MODE: str = "repl"

# Shared State
CLIENT_STATE = {
    "pending_approval_id": None,
    "last_tool_input": None # Context for approval
}

async def check_server(url: str) -> bool:
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url)
            return resp.status_code == 200
        except:
            return False

def start_server(host: str, port: int, yolo: bool):
    print("Starting background server...")
    cmd = [sys.executable, "-m", "aigent.main", "serve", "--host", host, "--port", str(port)]
    if yolo:
        cmd.append("--yolo")
    Popen(cmd, stdout=DEVNULL, stderr=DEVNULL, start_new_session=True)


async def ws_listener(ws, profile_config, ready_for_input: asyncio.Event, this_user_id: str = "cli-user"):
    """
    WebSocket listener that receives events and prints them.
    Buffers tokens to avoid excessive print_formatted_text calls.

    Note: We buffer tokens because calling print_formatted_text() for each individual
    token causes patch_stdout() to create excessive blank lines and cursor movements.
    By batching tokens, we dramatically reduce terminal control sequences.

    Args:
        ws: WebSocket connection
        profile_config: Profile configuration object
        ready_for_input: Event to signal when prompt should be active
        this_user_id: The user ID for this CLI client (to distinguish from other clients)
    """
    from prompt_toolkit import print_formatted_text
    from prompt_toolkit.formatted_text import HTML

    token_buffer = []
    last_flush_time = asyncio.get_event_loop().time()
    FLUSH_INTERVAL = 0.1  # Flush every 100ms

    async def flush_tokens():
        nonlocal token_buffer
        if token_buffer:
            # Print all buffered tokens at once using sys.stdout.write()
            # We avoid print_formatted_text() here because inside patch_stdout(),
            # it produces carriage returns (\r) and cursor movements that can
            # delete previously printed content. This is especially problematic
            # when receiving tokens for a message initiated by another client
            # in a shared session.
            sys.stdout.write(''.join(token_buffer))
            sys.stdout.flush()
            token_buffer = []

    try:
        async for message in ws:
            data = json.loads(message)
            event_type = data.get("type")
            content = data.get("content", "")
            metadata = data.get("metadata", {})

            if event_type == EventType.TOKEN:
                # Buffer tokens instead of printing immediately
                token_buffer.append(content)

                # Flush if enough time has passed or buffer is large
                current_time = asyncio.get_event_loop().time()
                if (current_time - last_flush_time > FLUSH_INTERVAL or
                    len(''.join(token_buffer)) > 100):
                    await flush_tokens()
                    last_flush_time = current_time

            else:
                # Flush any remaining tokens before handling other events
                await flush_tokens()

                if event_type == EventType.TOOL_START:
                    input_args = metadata.get("input", {})
                    formatted_args = ", ".join([f"{k}={repr(v)}" for k, v in input_args.items()])
                    limit = profile_config.tool_call_preview_length
                    if len(formatted_args) > limit:
                        formatted_args = formatted_args[:limit] + "..."
                    tool_name = content.replace("Calling tool: ", "")
                    print_formatted_text(HTML(f"<yellow>🛠  {tool_name}({formatted_args})</yellow>"))

                elif event_type == EventType.TOOL_END:
                    if len(content) > 500:
                        content = content[:500] + "..."
                    print_formatted_text(HTML(f"<grey>   {content}</grey>"))

                elif event_type == EventType.USER_INPUT:
                    # Another client sent a message - clear ready_for_input to pause the prompt
                    # This prevents patch_stdout() conflicts when printing the response
                    sender_id = metadata.get("user_id", "unknown")
                    if sender_id != this_user_id:
                        # Message from another client - pause our prompt
                        ready_for_input.clear()
                        # Use sys.stdout.write to avoid patch_stdout() cursor management issues
                        # that cause carriage returns and text deletion
                        sys.stdout.write(f"\033[36m[{sender_id}]\033[0m {content}\n")
                        sys.stdout.flush()

                elif event_type == EventType.ERROR:
                    print_formatted_text(HTML(f"<red>Error: {content}</red>"))
                    ready_for_input.set()

                elif event_type == EventType.SYSTEM:
                    print_formatted_text(HTML(f"<green>System: {content}</green>"))

                elif event_type == EventType.HISTORY_CONTENT:
                    # Just print the content as-is (it's already markdown text)
                    print_formatted_text(content)

                elif event_type == EventType.FINISH:
                    # End of turn - flush any remaining tokens and add newline
                    await flush_tokens()
                    # Use sys.stdout.write to avoid patch_stdout() cursor issues
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    ready_for_input.set()

                elif event_type == EventType.APPROVAL_REQUEST:
                    tool = metadata.get("tool")
                    args = metadata.get("input")
                    req_id = metadata.get("request_id")

                    CLIENT_STATE["pending_approval_id"] = req_id

                    print_formatted_text(HTML(f"<orange>✋ Permission Request: {tool}</orange>"))
                    print_formatted_text(f"   Args: {args}")
                    print_formatted_text(HTML("<b><orange>   Allow? [y/n/a(lways tool)/s(smart)]</orange></b>"))
                    ready_for_input.set()

    except websockets.ConnectionClosed:
        # Flush any remaining tokens before disconnecting
        await flush_tokens()
        print_formatted_text(HTML("<red>Connection to server lost.</red>"))
        pass

async def run_cli_prompt_toolkit(args: Any) -> None:
    """Run the legacy prompt_toolkit-based CLI.

    This is the original CLI implementation using prompt_toolkit.
    Kept for backwards compatibility.

    Args:
        args: Parsed command-line arguments.
    """
    pm = ProfileManager()
    config = pm.config

    host = config.server.host
    port = config.server.port
    base_url = f"http://{host}:{port}"

    # Session ID Strategy
    import uuid
    if hasattr(args, "session") and args.session:
        session_id = args.session
    else:
        # Default to ephemeral/random session
        session_id = f"cli-{uuid.uuid4().hex[:8]}"

    # Generate unique user ID for this CLI instance
    user_id = f"cli-{uuid.uuid4().hex[:8]}"
    ws_url = f"ws://{host}:{port}/ws/chat/{session_id}?profile={args.profile}&user_id={user_id}"

    # 1. Auto-Discovery / Start Server
    if hasattr(args, "replace") and args.replace:
        print("Replacing existing server...")
        kill_server_process(host=host, port=port)
        await asyncio.sleep(1)

    if not await check_server(base_url):
        start_server(host, port, args.yolo)
        # Wait loop
        for _ in range(10):
            await asyncio.sleep(1)
            if await check_server(base_url):
                break
        else:
            print("Failed to start server.")
            return

    # 2. Connect & Loop
    ready_for_input = asyncio.Event()
    ready_for_input.set()

    try:
        async with websockets.connect(ws_url) as ws:
            from prompt_toolkit import print_formatted_text
            print_formatted_text(HTML("<green>Connected to Aigent Server.</green>"))

            # Wrap everything in patch_stdout() so that background ws_listener
            # prints above the prompt instead of conflicting with it.
            # This is the recommended pattern from prompt_toolkit docs.
            with patch_stdout():
                # Start Listener
                listener = asyncio.create_task(ws_listener(ws, config, ready_for_input, user_id))

                # Setup Prompt
                slash_completer = WordCompleter(get_command_names(), ignore_case=True)
                session = PromptSession(completer=slash_completer)

                cmd_context = CommandContext(websocket=ws)

                try:
                    while True:
                        if listener.done():
                            break

                        # Wait until we're allowed to prompt again (after FINISH/approval)
                        await ready_for_input.wait()

                        # Dynamic Prompt
                        prompt_text = HTML("<b>> </b>")
                        if CLIENT_STATE["pending_approval_id"]:
                            prompt_text = HTML("<b><orange>Decision > </orange></b>")

                        try:
                            user_input = await session.prompt_async(prompt_text)
                        except (EOFError, KeyboardInterrupt):
                            break

                        if not user_input.strip():
                            continue

                        # Handle Approval Response
                        if CLIENT_STATE["pending_approval_id"]:
                            ans = user_input.lower().strip()
                            decision = "deny"
                            if ans in ['y', 'yes']: decision = "allow"
                            elif ans in ['n', 'no']: decision = "deny"
                            elif ans in ['a', 'always']: decision = "always_tool"
                            elif ans in ['s', 'smart']: decision = "always_smart"

                            msg = {
                                "type": "approval_response",
                                "request_id": CLIENT_STATE["pending_approval_id"],
                                "decision": decision
                            }
                            await ws.send(json.dumps(msg))
                            CLIENT_STATE["pending_approval_id"] = None
                            continue

                        # Handle Commands
                        if user_input.strip().startswith("/"):
                            if await handle_command(user_input, cmd_context):
                                if cmd_context.should_exit:
                                    break
                                continue

                        # Send Chat Message and wait for response before next prompt
                        ready_for_input.clear()
                        await ws.send(user_input)
                finally:
                    listener.cancel()

    except Exception as e:
        print(f"Error: {e}")


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
        sys.stderr.write("TUI mode not implemented yet\n")
        sys.exit(1)
    else:
        # Fallback to legacy prompt_toolkit mode
        await run_cli_prompt_toolkit(args)

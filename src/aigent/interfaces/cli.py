import asyncio
import sys
import json
import httpx
import websockets
from subprocess import Popen, DEVNULL
from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.completion import WordCompleter


from aigent.core.profiles import ProfileManager
from aigent.core.schemas import EventType
from aigent.interfaces.commands import get_command_names, handle_command, CommandContext
from aigent.server.lifecycle import kill_server_process

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


async def ws_listener(ws, profile_config):
    """
    WebSocket listener that receives events and prints them.
    Uses prompt_toolkit's print_formatted_text for all output to coordinate with the prompt.
    """
    current_line_length = 0

    try:
        async for message in ws:
            data = json.loads(message)
            event_type = data.get("type")
            content = data.get("content", "")
            metadata = data.get("metadata", {})

            if event_type == EventType.TOKEN:
                # Stream tokens without newline
                print_formatted_text(content, end="", flush=True)
                current_line_length += len(content)

            else:
                # Non-token event: ensure we start on a new line if we were streaming
                if event_type == EventType.TOOL_START:
                    # If we were streaming text, add a newline
                    if current_line_length > 0:
                        print_formatted_text("")
                        current_line_length = 0

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
                    print_formatted_text(HTML(f"<grey>{content}</grey>"))

                elif event_type == EventType.ERROR:
                    if current_line_length > 0:
                        print_formatted_text("")
                        current_line_length = 0
                    print_formatted_text(HTML(f"<red>Error: {content}</red>"))

                elif event_type == EventType.SYSTEM:
                    if current_line_length > 0:
                        print_formatted_text("")
                        current_line_length = 0
                    print_formatted_text(HTML(f"<green>System: {content}</green>"))

                elif event_type == EventType.HISTORY_CONTENT:
                    # Just print the content as-is (it's already markdown text)
                    if current_line_length > 0:
                        print_formatted_text("")  # Newline if needed
                        current_line_length = 0
                    print_formatted_text(content)

                elif event_type == EventType.FINISH:
                    # End of turn - ensure we have a newline
                    if current_line_length > 0:
                        print_formatted_text("")
                        current_line_length = 0

                elif event_type == EventType.APPROVAL_REQUEST:
                    if current_line_length > 0:
                        print_formatted_text("")
                        current_line_length = 0

                    tool = metadata.get("tool")
                    args = metadata.get("input")
                    req_id = metadata.get("request_id")

                    CLIENT_STATE["pending_approval_id"] = req_id

                    print_formatted_text(HTML(f"<orange>✋ Permission Request: {tool}</orange>"))
                    print_formatted_text(f"   Args: {args}")
                    print_formatted_text(HTML("<b><orange>   Allow? [y/n/a(lways tool)/s(smart)]</orange></b>"))

    except websockets.ConnectionClosed:
        print_formatted_text(HTML("<red>Connection to server lost.</red>"))
        pass

async def run_cli(args):
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

    ws_url = f"ws://{host}:{port}/ws/chat/{session_id}?profile={args.profile}&user_id=cli-user"

    # 1. Auto-Discovery / Start Server
    if hasattr(args, "replace") and args.replace:
        print(HTML("<yellow>Replacing existing server...</yellow>"))
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
    try:
        async with websockets.connect(ws_url) as ws:
            # Use patch_stdout for the ENTIRE session to coordinate all output
            with patch_stdout():
                print_formatted_text(HTML("<green>Connected to Aigent Server.</green>"))

                # Start Listener
                listener = asyncio.create_task(ws_listener(ws, config))

                # Setup Prompt
                slash_completer = WordCompleter(get_command_names(), ignore_case=True)
                session = PromptSession(completer=slash_completer)

                cmd_context = CommandContext(websocket=ws)

                while True:
                    if listener.done():
                        break

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

                    # Send Chat Message
                    await ws.send(user_input)

                listener.cancel()

    except Exception as e:
        console = Console()
        console.print(f"[red]Error: {e}[/red]")
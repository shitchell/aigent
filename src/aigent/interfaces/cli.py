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

from rich.console import Console
from rich.markdown import Markdown
from rich.live import Live

from aigent.core.profiles import ProfileManager
from aigent.core.schemas import EventType
from aigent.interfaces.commands import get_command_names, handle_command, CommandContext
from aigent.server.lifecycle import kill_server_process

console = Console()

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
    console.print("[yellow]Starting background server...[/yellow]")
    cmd = [sys.executable, "-m", "aigent.main", "serve", "--host", host, "--port", str(port)]
    if yolo:
        cmd.append("--yolo")
    Popen(cmd, stdout=DEVNULL, stderr=DEVNULL, start_new_session=True)

async def ws_listener(ws, profile_config):
    live_display = None
    current_text = ""
    
    try:
        async for message in ws:
            data = json.loads(message)
            event_type = data.get("type")
            content = data.get("content", "")
            metadata = data.get("metadata", {})
            
            if event_type == EventType.TOKEN:
                current_text += content
                if live_display is None:
                    live_display = Live(Markdown(current_text), console=console, refresh_per_second=10, transient=True)
                    live_display.start()
                else:
                    live_display.update(Markdown(current_text))
            
            else:
                # Stop Live Display
                if live_display:
                    live_display.stop()
                    live_display = None
                    # Print final result permanently
                    if current_text:
                        console.print(Markdown(current_text))
                    current_text = ""

                if event_type == EventType.TOOL_START:
                    input_args = metadata.get("input", {})
                    formatted_args = ", ".join([f"{k}={repr(v)}" for k, v in input_args.items()])
                    limit = profile_config.tool_call_preview_length
                    if len(formatted_args) > limit:
                        formatted_args = formatted_args[:limit] + "..."
                    tool_name = content.replace("Calling tool: ", "")
                    console.print(f"[yellow]🛠  {tool_name}({formatted_args})[/yellow]")
                    
                elif event_type == EventType.TOOL_END:
                    if len(content) > 500:
                        content = content[:500] + "..."
                    console.print(f"[grey50]{content}[/grey50]")
                    
                elif event_type == EventType.ERROR:
                    console.print(f"[red]Error: {content}[/red]")
                    
                elif event_type == EventType.SYSTEM:
                    console.print(f"[green]System: {content}[/green]")
                    
                elif event_type == EventType.HISTORY_CONTENT:
                    # Render history statically, no typing effect
                    console.print(Markdown(content))
                    
                elif event_type == EventType.APPROVAL_REQUEST:
                    tool = metadata.get("tool")
                    args = metadata.get("input")
                    req_id = metadata.get("request_id")
                    
                    CLIENT_STATE["pending_approval_id"] = req_id
                    
                    console.print(f"[orange1]✋ Permission Request: {tool}[/orange1]")
                    console.print(f"   Args: {args}")
                    console.print("[bold orange1]   Allow? [y/n/a(lways tool)/s(smart)][/bold orange1]")

    except websockets.ConnectionClosed:
        console.print("[red]Connection to server lost.[/red]")
        # We could try to reconnect or just exit
        # For now, just exit prompt loop?
        # sys.exit(0) is harsh if we are inside a task
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
        # We prefix with 'cli-' just for clarity in logs/files
        session_id = f"cli-{uuid.uuid4().hex[:8]}"
    
    ws_url = f"ws://{host}:{port}/ws/chat/{session_id}?profile={args.profile}&user_id=cli-user"

    # 1. Auto-Discovery / Start Server
    if hasattr(args, "replace") and args.replace:
        console.print("[yellow]Replacing existing server...[/yellow]")
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
            console.print("[green]Connected to Aigent Server.[/green]")
            
            # Start Listener
            listener = asyncio.create_task(ws_listener(ws, config))
            
            # Setup Prompt
            slash_completer = WordCompleter(get_command_names(), ignore_case=True)
            session = PromptSession(completer=slash_completer)
            
            cmd_context = CommandContext(console=console, websocket=ws)

            while True:
                if listener.done():
                    break
                    
                # Dynamic Prompt?
                prompt_text = HTML("<b>> </b>")
                if CLIENT_STATE["pending_approval_id"]:
                    prompt_text = HTML("<b><orange>Decision > </orange></b>")
                
                with patch_stdout():
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
                # We send raw text. The server treats it as user input.
                await ws.send(user_input)
                
            listener.cancel()
            
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")

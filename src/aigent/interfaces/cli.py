import asyncio
import sys
from prompt_toolkit import PromptSession, print_formatted_text as print
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.completion import WordCompleter

from rich.console import Console
from rich.markdown import Markdown
from rich.live import Live

from aigent.core.profiles import ProfileManager
from aigent.core.engine import AgentEngine
from aigent.core.schemas import EventType

console = Console()

async def run_cli(args):
    # 1. Load Profile
    profile_manager = ProfileManager()
    try:
        profile = profile_manager.get_profile(args.profile)
    except Exception as e:
        print(f"Error loading profile: {e}")
        return

    # 2. Initialize Engine
    engine = AgentEngine(profile, yolo=args.yolo)
    print(f"Initializing agent '{profile.name}'...")
    if args.yolo:
        print(HTML("<red><b>WARNING: YOLO Mode Enabled. Permissions checks DISABLED.</b></red>"))

    try:
        await engine.initialize()
    except Exception as e:
        print(f"Initialization failed: {e}")
        return

    # 3. REPL Loop
    slash_commands = ['/clear', '/reset', '/help', '/exit', '/quit']
    slash_completer = WordCompleter(slash_commands, ignore_case=True)
    
    session = PromptSession(completer=slash_completer)
    
    print(HTML("<b><green>Ready! Type 'exit' to quit.</green></b>"))

    while True:
        with patch_stdout():
            try:
                user_input = await session.prompt_async(HTML("<b>> </b>"))
            except (EOFError, KeyboardInterrupt):
                break
            
            # --- Slash Commands ---
            cmd = user_input.strip().lower()
            if cmd in ["exit", "quit"]:
                break
            if cmd == "/clear":
                console.clear()
                continue
            if cmd == "/reset":
                # Keep only system prompt (index 0)
                if engine.history:
                    engine.history = [engine.history[0]]
                print(HTML("<green>History cleared.</green>"))
                continue
            if cmd == "/help":
                print(HTML("<b>Commands:</b> /clear, /reset, /exit"))
                continue

            if not user_input.strip():
                continue

            # Process input
            try:
                # print(HTML(f"<skyblue>Thinking...</skyblue>"))
                
                # Markdown Streaming Buffer
                current_text = ""
                live_display = None
                
                async for event in engine.stream(user_input):
                    
                    if event.type == EventType.TOKEN:
                        current_text += event.content
                        
                        # Start Live display if not active
                        if live_display is None:
                            live_display = Live(Markdown(current_text), console=console, refresh_per_second=10)
                            live_display.start()
                        else:
                            live_display.update(Markdown(current_text))
                        
                    else:
                        # Non-token event: Stop live display if running
                        if live_display:
                            live_display.stop()
                            live_display = None
                            current_text = "" # Reset buffer for next chunk? 
                            # Ideally we shouldn't reset if we want to keep previous text visible?
                            # live.stop() leaves the content on screen. So we are good.
                        
                        if event.type == EventType.TOOL_START:
                            # Format Input
                            input_args = event.metadata.get("input", {})
                            formatted_args = ", ".join([f"{k}={repr(v)}" for k, v in input_args.items()])
                            
                            # Truncate
                            limit = profile_manager.config.tool_call_preview_length
                            if len(formatted_args) > limit:
                                formatted_args = formatted_args[:limit] + "..."
                                
                            tool_name = event.content.replace("Calling tool: ", "")
                            print(HTML(f"<yellow>🛠  {tool_name}({formatted_args})</yellow>"))
                            
                        elif event.type == EventType.TOOL_END:
                            # Format output
                            content = event.content
                            # Truncate total length if massive
                            if len(content) > 500:
                                content = content[:500] + "..."
                            print(HTML(f"<grey>{content}</grey>"))
                            
                        elif event.type == EventType.ERROR:
                            print(HTML(f"<red>Error: {event.content}</red>"))

                        elif event.type == EventType.APPROVAL_REQUEST:
                            tool = event.metadata.get("tool")
                            args = event.metadata.get("input")
                            req_id = event.metadata.get("request_id")
                            
                            print(HTML(f"<orange>✋ Permission Request: {tool}</orange>"))
                            print(f"   Args: {args}")
                            
                            decision = "deny"
                            while True:
                                ans = await session.prompt_async(HTML("   <orange>Allow? [y/n/a(lways tool)/s(smart)]: </orange>"))
                                ans = ans.lower().strip()
                                if ans in ['y', 'yes']:
                                    decision = "allow"
                                    break
                                elif ans in ['n', 'no']:
                                    decision = "deny"
                                    break
                                elif ans in ['a', 'always']:
                                    decision = "always_tool"
                                    break
                                elif ans in ['s', 'smart']:
                                    decision = "always_smart"
                                    break
                            
                            # Send decision back to engine
                            if req_id:
                                engine.authorizer.resolve_request(str(req_id), {"decision": decision})

                # Clean up at end of stream
                if live_display:
                    live_display.stop()
                    
            except Exception as e:
                print(f"Error during execution: {e}")

import asyncio
import sys
from prompt_toolkit import PromptSession, print_formatted_text as print
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.formatted_text import HTML

from aigent.core.profiles import ProfileManager
from aigent.core.engine import AgentEngine
from aigent.core.schemas import EventType

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
    session = PromptSession()
    
    print(HTML("<b><green>Ready! Type 'exit' to quit.</green></b>"))

    while True:
        with patch_stdout():
            try:
                user_input = await session.prompt_async(HTML("<b>> </b>"))
            except (EOFError, KeyboardInterrupt):
                break

            if user_input.strip().lower() in ["exit", "quit"]:
                break
            
            if not user_input.strip():
                continue

            # Process input
            try:
                print(HTML(f"<skyblue>Thinking...</skyblue>"))
                
                # We track if we are currently printing a token stream to handle newlines
                streaming_text = False
                
                async for event in engine.stream(user_input):
                    
                    if event.type == EventType.TOKEN:
                        sys.stdout.write(event.content)
                        sys.stdout.flush()
                        streaming_text = True
                        
                    elif event.type == EventType.TOOL_START:
                        if streaming_text:
                            sys.stdout.write("\n")
                            streaming_text = False
                            
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
                        if streaming_text:
                            sys.stdout.write("\n")
                            streaming_text = False
                            
                        tool = event.metadata.get("tool")
                        args = event.metadata.get("input")
                        req_id = event.metadata.get("request_id")
                        
                        print(HTML(f"<orange>✋ Permission Request: {tool}</orange>"))
                        print(f"   Args: {args}")
                        
                        # Prompt user
                        # We need to break out of patch_stdout to prompt properly?
                        # Or use session inside? 
                        # Since we are inside patch_stdout context, print works.
                        # But prompt_async?
                        
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
                        engine.authorizer.resolve_request(req_id, {"decision": decision})

                if streaming_text:
                    sys.stdout.write("\n")
                    
            except Exception as e:
                print(f"Error during execution: {e}")

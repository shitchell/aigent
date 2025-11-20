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
    engine = AgentEngine(profile)
    print(f"Initializing agent '{profile.name}'...")
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
                        # We don't truncate Output here (or do we want to?)
                        # Current code truncates to 100 chars.
                        # Maybe we should respect the config setting too?
                        # But output is usually huge. Let's stick to 100 or make output_preview_length?
                        # For now, let's assume tool_call_preview_length applies to input args only as requested.
                        print(HTML(f"<grey>   -> {event.content[:100]}...</grey>"))
                        
                    elif event.type == EventType.ERROR:
                        print(HTML(f"<red>Error: {event.content}</red>"))

                if streaming_text:
                    sys.stdout.write("\n")
                    
            except Exception as e:
                print(f"Error during execution: {e}")

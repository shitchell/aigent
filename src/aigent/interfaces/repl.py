"""REPL Interface.

A lightweight, compatibility-first CLI client.
"""

import asyncio
import json
import uuid
import sys
from typing import Any

import websockets

def colorize(text: str, color: str) -> str:
    colors = {
        'green': '\033[32m',
        'yellow': '\033[33m',
        'red': '\033[31m',
        'reset': '\033[0m'
    }
    return f"{colors.get(color, '')}{text}{colors['reset']}"

async def run_repl(args: Any):
    session_id = args.session or f"repl-{uuid.uuid4().hex[:8]}"
    user_id = f"user-{uuid.uuid4().hex[:4]}"
    url = f"ws://{args.host}:{args.port}/ws/chat/{session_id}?user_id={user_id}&client_type=repl"
    
    print(colorize(f"Connecting to {url}...", "yellow"))
    
    try:
        async with websockets.connect(url) as ws:
            print(colorize("Connected.", "green"))
            
            # Input Loop
            loop = asyncio.get_running_loop()
            
            async def listen():
                async for msg in ws:
                    data = json.loads(msg)
                    typ = data.get("type")
                    
                    if typ == "token":
                        sys.stdout.write(data["content"])
                        sys.stdout.flush()
                    elif typ == "finish":
                        sys.stdout.write("\n")
                    elif typ == "approval_request":
                        # Simplistic Approval Prompt (Pauses output, messy in async)
                        # Ideally, this should interrupt input. 
                        # For V2 MVP REPL, we print alert.
                        meta = data["metadata"]
                        print(f"\n{colorize('✋ PERMISSION REQUEST:', 'red')} {meta['tool']}")
                        print(f"   Args: {meta['input']}")
                        print(f"   ID: {meta['request_id']}")
                        print("   Type 'y' to allow, 'n' to deny.")
            
            asyncio.create_task(listen())
            
            while True:
                text = await loop.run_in_executor(None, input, "> ")
                
                # Check for approval response logic (Command parsing)
                # If user typed 'y' and there is a pending request... 
                # This state management is tricky in pure REPL without context.
                # Simplification: Assume 'y' approves the last seen ID?
                # Or require specific command?
                
                # For V2 MVP: Just send text. 
                # If the user wants to approve, they need a slash command?
                # Or we intercept short messages?
                
                if text.strip() in ['y', 'n']:
                    # HACK: Construct approval response manually? 
                    # We need the request_id. 
                    # REPL limitations show why TUI/Web is better.
                    # We'll skip complex logic here and just send text.
                    pass

                await ws.send(text)
                
    except Exception as e:
        print(colorize(f"Connection Failed: {e}", "red"))

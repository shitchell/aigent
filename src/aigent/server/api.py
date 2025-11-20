import asyncio
import json
from pathlib import Path
from typing import Dict, List
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, messages_to_dict, messages_from_dict

from aigent.core.engine import AgentEngine
from aigent.core.profiles import ProfileManager
from aigent.core.schemas import AgentEvent, EventType

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

app = FastAPI()

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

SESSIONS_DIR = Path.home() / ".aigent" / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

class ConnectionManager:
    def __init__(self):
        # session_id -> List[WebSocket]
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # session_id -> AgentEngine
        self.sessions: Dict[str, AgentEngine] = {}
        # session_id -> Lock (to prevent concurrent engine runs in same session)
        self.locks: Dict[str, asyncio.Lock] = {}

    async def connect(self, websocket: WebSocket, session_id: str, profile_name: str = "default") -> bool:
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)

        # Initialize Engine if needed
        if session_id not in self.sessions:
            # Try to load from disk first
            if not await self._load_session_from_disk(session_id):
                # If no save file, create new with requested profile
                try:
                    pm = ProfileManager()
                    # Fallback to default if requested profile doesn't exist
                    try:
                        profile = pm.get_profile(profile_name)
                    except Exception:
                        print(f"Profile {profile_name} not found, falling back to default")
                        profile = pm.get_profile("default")
                        
                    engine = AgentEngine(profile)
                    await engine.initialize()
                    self.sessions[session_id] = engine
                except Exception as e:
                    print(f"Failed to initialize engine: {e}")
                    await websocket.close(code=1000, reason=f"Init failed: {str(e)}")
                    return False
            
            self.locks[session_id] = asyncio.Lock()

        # Replay History to this new connection
        await self.replay_history(session_id, websocket)
        return True

    def disconnect(self, websocket: WebSocket, session_id: str):
        if session_id in self.active_connections:
            if websocket in self.active_connections[session_id]:
                self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                # Optional: Clean up session engine if empty? 
                # For now, keep it alive for persistence.
                pass

    async def broadcast(self, session_id: str, message: str):
        """Sends a raw string (JSON) to all sockets in a session"""
        if session_id not in self.active_connections:
            return
        
        # Copy list to avoid modification during iteration issues
        for connection in list(self.active_connections[session_id]):
            try:
                await connection.send_text(message)
            except Exception:
                # Handle dead sockets
                pass

    async def replay_history(self, session_id: str, websocket: WebSocket):
        """Converts LangChain history to AgentEvents and sends them"""
        engine = self.sessions[session_id]
        
        for msg in engine.history:
            if isinstance(msg, HumanMessage):
                # Replay User Input
                event = AgentEvent(type=EventType.USER_INPUT, content=str(msg.content))
                await websocket.send_text(event.to_json())
            
            elif isinstance(msg, AIMessage):
                # 1. Replay Content (Thought/Answer)
                if msg.content:
                    event = AgentEvent(type=EventType.TOKEN, content=str(msg.content))
                    await websocket.send_text(event.to_json())
                
                # 2. Replay Tool Calls
                # tool_calls is a list of dicts: [{'name': 'foo', 'args': {...}, 'id': ...}]
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        event = AgentEvent(
                            type=EventType.TOOL_START, 
                            content=f"Calling tool: {tool_call['name']}",
                            metadata={"input": tool_call['args'], "tool_call_id": tool_call['id']}
                        )
                        await websocket.send_text(event.to_json())
                
                if not msg.tool_calls:
                    await websocket.send_text(AgentEvent(type=EventType.FINISH).to_json())

            elif isinstance(msg, ToolMessage):
                # Replay Tool Output
                event = AgentEvent(
                    type=EventType.TOOL_END, 
                    content=str(msg.content),
                    metadata={"tool_call_id": msg.tool_call_id}
                )
                await websocket.send_text(event.to_json())

        # Final cleanup: Ensure the last message isn't stuck "Typing..."
        if engine.history and isinstance(engine.history[-1], (AIMessage, ToolMessage)):
             await websocket.send_text(AgentEvent(type=EventType.FINISH).to_json())

    async def _save_session_to_disk(self, session_id: str):
        """Saves the current engine history to disk."""
        if session_id not in self.sessions:
            return
            
        engine = self.sessions[session_id]
        # Convert messages to dicts
        history_dicts = messages_to_dict(engine.history)
        
        data = {
            "profile": engine.profile.name,
            "history": history_dicts
        }
        
        file_path = SESSIONS_DIR / f"{session_id}.json"
        try:
            with open(file_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Failed to save session {session_id}: {e}")

    async def _load_session_from_disk(self, session_id: str) -> bool:
        """Attempts to load session history from disk. Returns True if successful."""
        file_path = SESSIONS_DIR / f"{session_id}.json"
        if not file_path.exists():
            return False
            
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
            
            # Handle legacy files (list of messages) vs new format (dict)
            if isinstance(data, list):
                history_dicts = data
                profile_name = "default"
            else:
                history_dicts = data.get("history", [])
                profile_name = data.get("profile", "default")
            
            messages = messages_from_dict(history_dicts)
            
            # Re-hydrate engine with correct profile
            pm = ProfileManager()
            try:
                profile = pm.get_profile(profile_name)
            except:
                profile = pm.get_profile("default")
                
            engine = AgentEngine(profile)
            await engine.initialize()
            
            # Inject history
            engine.history = messages
            self.sessions[session_id] = engine
            return True
            
        except Exception as e:
            print(f"Failed to load session {session_id}: {e}")
            return False

manager = ConnectionManager()

@app.get("/")
async def get():
    return FileResponse('static/index.html')

@app.get("/api/profiles")
async def get_profiles():
    pm = ProfileManager()
    # Ensure we load profiles
    if not pm.loaded:
        pm.load_profiles()
    return list(pm._profiles.keys())

@app.websocket("/ws/chat/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
    session_id: str,
    user_id: str = Query("anon"),
    profile: str = Query("default")
):
    success = await manager.connect(websocket, session_id, profile)
    if not success:
        return
    
    try:
        while True:
            data = await websocket.receive_text()
            
            # 1. Broadcast the User's Input to everyone (so they see "User said X")
            # We construct an event for this.
            user_event = AgentEvent(
                type=EventType.USER_INPUT, 
                content=data,
                metadata={"user_id": user_id}
            )
            await manager.broadcast(session_id, user_event.to_json())
            
            # 2. Run the Engine (Protected by Lock)
            engine = manager.sessions[session_id]
            lock = manager.locks[session_id]
            
            async with lock:
                async for event in engine.stream(data):
                    # Broadcast AI events (Tokens, Tools) to ALL users
                    await manager.broadcast(session_id, event.to_json())
                
                # AUTO-SAVE after turn
                await manager._save_session_to_disk(session_id)
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
        # Optional: Broadcast "User left"

async def run_server(args):
    config = uvicorn.Config(app, host=args.host, port=args.port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
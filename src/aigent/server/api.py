import asyncio
import json
from pathlib import Path
from typing import Dict, List, Any
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
        self.yolo_mode: bool = False

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
                        
                    engine = AgentEngine(profile, yolo=self.yolo_mode)
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
                meta = {}
                if msg.name:
                    meta["user_id"] = msg.name
                    
                event = AgentEvent(type=EventType.USER_INPUT, content=str(msg.content), metadata=meta)
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
                
            engine = AgentEngine(profile, yolo=self.yolo_mode)
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

@app.get("/api/config")
async def get_config():
    pm = ProfileManager()
    if not pm.loaded:
        pm.load_profiles()
    return pm.config.dict()

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
            
            # Determine if it's a chat message or a control message (JSON)
            try:
                msg = json.loads(data)
                if isinstance(msg, dict) and msg.get("type") == "approval_response":
                    # Handle Approval
                    engine = manager.sessions[session_id]
                    req_id = msg.get("request_id")
                    if engine.authorizer and req_id:
                        engine.authorizer.resolve_request(str(req_id), msg)
                    continue
            except json.JSONDecodeError:
                pass # Treat as raw chat message

            # Treat as chat input
            user_input = data
            
            # 1. Broadcast User Input
            user_event = AgentEvent(
                type=EventType.USER_INPUT, 
                content=user_input,
                metadata={"user_id": user_id}
            )
            await manager.broadcast(session_id, user_event.to_json())
            
            # 2. Run Engine in Background Task
            # We fire and forget (but we track it?)
            # We need to ensure sequential execution for a single session?
            # manager.locks ensures that.
            # We launch a task that acquires the lock.
            
            asyncio.create_task(process_chat_message(session_id, user_input, user_name=user_id))
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)

async def process_chat_message(session_id: str, user_input: str, user_name: str = None):
    """Background task to run the engine"""
    engine = manager.sessions.get(session_id)
    if not engine:
        return

    lock = manager.locks.get(session_id)
    if not lock:
        return
        
    # Acquire lock to ensure we don't run multiple turns at once
    async with lock:
        try:
            async for event in engine.stream(user_input, user_name=user_name):
                await manager.broadcast(session_id, event.to_json())
            
            await manager._save_session_to_disk(session_id)
        except Exception as e:
            print(f"Error in chat processing: {e}")
            error_event = AgentEvent(type=EventType.ERROR, content=str(e))
            await manager.broadcast(session_id, error_event.to_json())

async def run_server(args) -> None:
    """
    Starts the Uvicorn server for the Web Daemon.
    
    Args:
        args: Parsed command line arguments (host, port, yolo).
    """
    manager.yolo_mode = args.yolo
    if args.yolo:
        print("\033[91mWARNING: Server running in YOLO Mode. All permission checks are DISABLED.\033[0m")
        
    config = uvicorn.Config(app, host=args.host, port=args.port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
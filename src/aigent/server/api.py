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

from aigent.core.persistence import SessionManager

app = FastAPI()

SESSIONS_DIR = Path.home() / ".aigent" / "sessions"

class ConnectionManager:
    def __init__(self):
        # session_id -> List[WebSocket]
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # session_id -> AgentEngine
        self.sessions: Dict[str, AgentEngine] = {}
        # session_id -> Lock (to prevent concurrent engine runs in same session)
        self.locks: Dict[str, asyncio.Lock] = {}
        self.yolo_mode: bool = False
        
        self.session_manager = SessionManager(SESSIONS_DIR)
        self.shutdown_task: Any = None # asyncio.Task

    def _start_shutdown_timer(self):
        """Starts a timer to kill the server if no connections exist."""
        if self.shutdown_task:
            self.shutdown_task.cancel()
        
        async def shutdown():
            print("No active connections. Shutting down in 30 seconds...")
            try:
                await asyncio.sleep(30)
                print("Shutting down server due to inactivity.")
                # Force save all sessions? They are saved incrementally.
                import os, signal
                os.kill(os.getpid(), signal.SIGINT)
            except asyncio.CancelledError:
                pass
            
        self.shutdown_task = asyncio.create_task(shutdown())

    def _cancel_shutdown_timer(self):
        if self.shutdown_task:
            self.shutdown_task.cancel()
            self.shutdown_task = None
            # print("Shutdown cancelled.")

    async def connect(self, websocket: WebSocket, session_id: str, profile_name: str = "default") -> bool:
        self._cancel_shutdown_timer()
        
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)

        # Initialize Engine if needed
        if session_id not in self.sessions:
            # Try to load from persistence
            session_data = await self.session_manager.load_session(session_id)
            
            if session_data:
                # Rehydrate
                profile_name = session_data.get("profile", "default")
                # ... (continue to init engine)
            
            # Profile Loading logic
            try:
                pm = ProfileManager()
                try:
                    profile = pm.get_profile(profile_name)
                except Exception:
                    print(f"Profile {profile_name} not found, falling back to default")
                    profile = pm.get_profile("default")
                    
                engine = AgentEngine(profile, yolo=self.yolo_mode)
                await engine.initialize()
                
                # Inject History if loaded
                if session_data and "history" in session_data:
                    engine.history = session_data["history"]
                    
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
                # Cleanup empty session list?
                del self.active_connections[session_id]
                pass
                
        # Check GLOBAL connections
        total_connections = sum(len(conns) for conns in self.active_connections.values())
        print(f"Connection closed. Total active: {total_connections}")
        
        if total_connections == 0:
            self._start_shutdown_timer()

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
                    event = AgentEvent(type=EventType.HISTORY_CONTENT, content=str(msg.content))
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

manager = ConnectionManager()

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

@app.get("/api/stats")
async def get_stats():
    total = sum(len(conns) for conns in manager.active_connections.values())
    return {
        "active_connections": total,
        "sessions": list(manager.active_connections.keys()),
        "shutdown_scheduled": manager.shutdown_task is not None
    }

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
                if isinstance(msg, dict):
                    if msg.get("type") == "approval_response":
                        # Handle Approval
                        engine = manager.sessions[session_id]
                        req_id = msg.get("request_id")
                        if engine.authorizer and req_id:
                            engine.authorizer.resolve_request(str(req_id), msg)
                        continue
                    elif msg.get("type") == "command":
                        # Handle /slash commands from client
                        cmd = msg.get("content")
                        engine = manager.sessions[session_id]
                        if cmd == "/reset":
                            if engine.history:
                                engine.history = [engine.history[0]]
                            # Broadcast confirmation
                            # We don't have a generic "System Message" event type in schema yet?
                            # Let's use ERROR type for visibility or create SYSTEM type. 
                            # We have EventType.SYSTEM defined in schemas.py!
                            await manager.broadcast(session_id, AgentEvent(type=EventType.SYSTEM, content="History reset.").to_json())
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
            
            # Save State
            await manager.session_manager.save_session(session_id, engine.profile.name, engine.history)
            
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
    import os
    pid_file = Path.home() / ".aigent" / "server.pid"
    try:
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(os.getpid()))
    except Exception as e:
        print(f"Warning: Could not write PID file: {e}")

    manager.yolo_mode = args.yolo
    if args.yolo:
        print("\033[91mWARNING: Server running in YOLO Mode. All permission checks are DISABLED.\033[0m")
    
    # Dynamic Static Mount
    pm = ProfileManager()
    pm.load_profiles()
    static_dir = pm.config.server.static_dir
    static_path = Path(static_dir).expanduser().resolve()
    
    if not static_path.exists():
        print(f"\033[93mWarning: Static directory not found at {static_path}. Web UI may not work.\033[0m")
    
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
    
    @app.get("/")
    async def root():
        return FileResponse(static_path / "index.html")
        
    config = uvicorn.Config(app, host=args.host, port=args.port, log_level="info")
    server = uvicorn.Server(config)
    
    try:
        await server.serve()
    finally:
        if pid_file.exists():
            try:
                pid_file.unlink()
            except Exception:
                pass
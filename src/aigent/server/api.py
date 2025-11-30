"""WebSocket API and Server Gateway.

This module acts as the bridge between the external world (WebSockets)
and the internal Event Bus.
"""

import asyncio
import json
import os
import signal
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from aigent.core.events import bus, handles, CoreSignal
from aigent.core.schemas import (
    User,
    Session,
    ClientType,
    ClientInput,
    ApprovalRequest,
    ApprovalResponse,
    Message,
    RoleType,
)
from aigent.core.persistence import session_store
from aigent.core.logging import get_logger
from aigent.core.profiles import profiles
from aigent.handlers.tools import ToolSignal
from aigent.handlers.llm import LLMSignal

# Import Handlers to Register them
import aigent.handlers.session
import aigent.handlers.tools
import aigent.handlers.llm
import aigent.handlers.commands

logger = get_logger(__name__)

app = FastAPI()

# Mount Static Files (Web UI)
try:
    # Assume static/ is in project root
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception:
    logger.warning("Static directory not found. Web UI disabled.")

@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.get("/api/health")
async def health_check():
    """Return server status and PID."""
    return {
        "status": "ok",
        "pid": os.getpid(),
        "active_connections": sum(len(c) for c in manager.active_connections.values())
    }

@app.get("/api/profiles")
async def get_profiles():
    """Return list of available profiles."""
    if not profiles.loaded:
        profiles.load()
    return list(profiles.config.profiles.keys())

@app.get("/api/config")
async def get_config():
    """Return global settings."""
    if not profiles.loaded:
        profiles.load()
    return profiles.config.settings.model_dump()

# --- Connection Manager ---

class ConnectionManager:
    def __init__(self):
        # session_id -> list[WebSocket]
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.shutdown_task: Optional[asyncio.Task] = None
        
    def _cancel_shutdown(self):
        if self.shutdown_task:
            logger.info("New connection: Server shutdown cancelled.")
            self.shutdown_task.cancel()
            self.shutdown_task = None

    def _schedule_shutdown(self):
        if self.shutdown_task:
            return
            
        async def shutdown_timer():
            logger.info("No active connections. Server shutting down in 60s...")
            try:
                await asyncio.sleep(60)
                logger.info("Server shutting down due to inactivity.")
                os.kill(os.getpid(), signal.SIGTERM)
            except asyncio.CancelledError:
                pass
                
        self.shutdown_task = asyncio.create_task(shutdown_timer())

    async def connect(self, websocket: WebSocket, session_id: str):
        self._cancel_shutdown()
        
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        logger.info(f"Client connected to session {session_id}")

    def disconnect(self, websocket: WebSocket, session_id: str):
        if session_id in self.active_connections:
            if websocket in self.active_connections[session_id]:
                self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
                
        # Check global count
        total = sum(len(c) for c in self.active_connections.values())
        if total == 0:
            self._schedule_shutdown()

    async def broadcast(self, session_id: str, message: Dict[str, Any]):
        if session_id not in self.active_connections:
            return
        
        # Serialize once
        text = json.dumps(message)
        for connection in list(self.active_connections[session_id]): # Copy list for safety
            try:
                await connection.send_text(text)
            except Exception as e:
                logger.warning(f"Failed to send to client: {e}")

manager = ConnectionManager()

# --- Handlers (Outbound: Bus -> WebSocket) ---

@handles(LLMSignal.TOKEN_STREAM)
async def on_llm_token(content: str, session: Session):
    """Broadcast tokens."""
    await manager.broadcast(session.id, {
        "type": "token",
        "content": content
    })

@handles(CoreSignal.SYSTEM_ERROR)
async def on_system_error(exception: Exception, session: Session, **kwargs):
    """Broadcast errors."""
    await manager.broadcast(session.id, {
        "type": "error",
        "content": str(exception)
    })

@handles(CoreSignal.SYSTEM_OUTPUT)
async def on_system_output(content: str, session: Session):
    """Send text response to clients."""
    await manager.broadcast(
        session.id,
        {
            "type": "history_content",
            "content": content,
        },
    )
    # Also send finish?
    await manager.broadcast(session.id, {"type": "finish"})

@handles(ToolSignal.APPROVAL_REQUESTED)
async def on_approval_requested(
    request_id: str, tool_name: str, tool_input: Dict[str, Any], session: Session
):
    """Broadcast approval request."""
    await manager.broadcast(
        session.id,
        {
            "type": "approval_request",
            "metadata": {"request_id": request_id, "tool": tool_name, "input": tool_input},
        },
    )

@handles(ToolSignal.EXECUTE_SUCCESS)
async def on_tool_success(request_id: str, result: str, session: Session):
    """Broadcast tool result."""
    await manager.broadcast(session.id, {"type": "tool_end", "content": result})

# --- WebSocket Endpoint (Inbound: WebSocket -> Bus) ---

@app.websocket("/ws/chat/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    user_id: str = Query("anon"),
    profile: str = Query("default"),
    client_type: str = Query("unknown"),
):
    await manager.connect(websocket, session_id)
    
    # Load Session & Create User
    session = await session_store.load_session(session_id)
    if profile != "default":
        session.profile = profile
        
    user = User(id=user_id, name=user_id, client_type=client_type)
    
    # Notify System (Connect)
    await bus.dispatch(CoreSignal.CLIENT_CONNECT, session=session, user=user, websocket=websocket)

    # Replay History
    for msg in session.history:
        if msg.role == RoleType.USER:
            await manager.broadcast(
                session_id,
                {"type": "user_input", "content": msg.content, "metadata": msg.metadata},
            )
        elif msg.role == RoleType.ASSISTANT:
            await manager.broadcast(
                session_id,
                {"type": "history_content", "content": msg.content, "metadata": msg.metadata},
            )
        elif msg.role == RoleType.TOOL:
            await manager.broadcast(
                session_id,
                {"type": "tool_end", "content": msg.content, "metadata": msg.metadata},
            )
    
    # Send finish to ensure UI state is clean
    await manager.broadcast(session_id, {"type": "finish"})

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg_json = json.loads(data)
                if isinstance(msg_json, dict) and msg_json.get("type") == "approval_response":
                    await bus.dispatch(
                        ToolSignal.APPROVAL_RESOLVED,
                        request_id=msg_json["request_id"],
                        decision=msg_json["decision"],
                        session=session,
                        user=user,
                    )
                    continue
            except json.JSONDecodeError:
                pass

            msg_obj = Message(role="user", content=data, metadata={"user_id": user.id})
            
            await manager.broadcast(
                session_id,
                {"type": "user_input", "content": data, "metadata": {"user_id": user.id}},
            )
            
            await bus.dispatch(
                CoreSignal.CLIENT_INPUT_RECEIVED, session=session, user=user, message=msg_obj
            )
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
        await bus.dispatch(CoreSignal.CLIENT_DISCONNECT, session=session, user=user)

async def run_server(host: str = "127.0.0.1", port: int = 8000):
    """Start the Uvicorn server."""
    # We don't use 'app' string here because we are running programmatically
    config = uvicorn.Config(app, host=host, port=port)
    server = uvicorn.Server(config)
    await server.serve()
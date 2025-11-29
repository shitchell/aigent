"""WebSocket API and Server Gateway.

This module acts as the bridge between the external world (WebSockets)
and the internal Event Bus.
"""

import asyncio
import json
from typing import Dict, List, Any

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
from aigent.handlers.tools import ToolSignal

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

# --- Connection Manager ---

class ConnectionManager:
    def __init__(self):
        # session_id -> list[WebSocket]
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # session_id -> Session (Cache?)
        # For V2, we load session on every request or cache it?
        # Loading from persistence is safer for now.
        
    async def connect(self, websocket: WebSocket, session_id: str):
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

    async def broadcast(self, session_id: str, message: Dict[str, Any]):
        if session_id not in self.active_connections:
            return
        
        # Serialize once
        text = json.dumps(message)
        for connection in self.active_connections[session_id]:
            try:
                await connection.send_text(text)
            except Exception as e:
                logger.warning(f"Failed to send to client: {e}")

manager = ConnectionManager()

# --- Handlers (Outbound: Bus -> WebSocket) ---

@handles(CoreSignal.SYSTEM_OUTPUT)
async def on_system_output(content: str, session: Session):
    """Send text response to clients."""
    await manager.broadcast(session.id, {
        "type": "token", # Use legacy type for frontend compat? Or new?
        # Frontend expects 'token' for streaming or 'history_content'.
        # Let's use 'token' for now.
        "content": content
    })
    # Also send finish?
    await manager.broadcast(session.id, {"type": "finish"})

@handles(ToolSignal.APPROVAL_REQUESTED)
async def on_approval_requested(
    request_id: str, 
    tool_name: str, 
    tool_input: Dict[str, Any], 
    session: Session
):
    """Broadcast approval request."""
    await manager.broadcast(session.id, {
        "type": "approval_request",
        "metadata": {
            "request_id": request_id,
            "tool": tool_name,
            "input": tool_input
        }
    })

@handles(ToolSignal.EXECUTE_SUCCESS)
async def on_tool_success(request_id: str, result: str, session: Session):
    """Broadcast tool result."""
    await manager.broadcast(session.id, {
        "type": "tool_end",
        "content": result
    })

# --- WebSocket Endpoint (Inbound: WebSocket -> Bus) ---

@app.websocket("/ws/chat/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    user_id: str = Query("anon"),
    profile: str = Query("default"),
    client_type: str = Query("unknown") # Expecting "web", "tui", "repl"
):
    await manager.connect(websocket, session_id)
    
    # Load Session & Create User
    session = await session_store.load_session(session_id)
    # Update profile if not set or if user requested specific (logic customizable)
    if profile != "default":
        session.profile = profile
        
    user = User(id=user_id, name=user_id, client_type=client_type) # Simple mapping
    
    # Notify System (Connect)
    await bus.dispatch(CoreSignal.CLIENT_CONNECT, session=session, user=user, websocket=websocket)

    try:
        while True:
            data = await websocket.receive_text()
            
            # Parse JSON or Raw Text?
            # V1 frontend sends raw text for chat, but JSON for approvals/commands.
            try:
                msg_json = json.loads(data)
                
                # Check for Approval Response
                if isinstance(msg_json, dict) and msg_json.get("type") == "approval_response":
                    await bus.dispatch(
                        ToolSignal.APPROVAL_RESOLVED,
                        request_id=msg_json["request_id"],
                        decision=msg_json["decision"],
                        session=session,
                        user=user
                    )
                    continue
                    
                # Check for Commands? (V2: /reset is handled by frontend or backend? Let's say raw text)
                
            except json.JSONDecodeError:
                pass # Treat as chat input

            # It's a Chat Message
            # 1. Create Message Object
            msg_obj = Message(
                role="user",
                content=data,
                metadata={"user_id": user.id}
            )
            
            # 2. Broadcast Echo (UX)
            await manager.broadcast(session_id, {
                "type": "user_input",
                "content": data,
                "metadata": {"user_id": user.id}
            })
            
            # 3. Dispatch to Core
            await bus.dispatch(
                CoreSignal.CLIENT_INPUT_RECEIVED,
                session=session,
                user=user,
                message=msg_obj
            )
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
        await bus.dispatch(CoreSignal.CLIENT_DISCONNECT, session=session, user=user)

async def run_server(host: str = "127.0.0.1", port: int = 8000):
    """Start the Uvicorn server."""
    config = uvicorn.Config(app, host=host, port=port)
    server = uvicorn.Server(config)
    await server.serve()

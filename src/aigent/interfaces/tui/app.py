"""Main TUI application for Aigent.

This module implements the Textual-based TUI application for Aigent,
including WebSocket connection handling, message display, and user input.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional, Any, Dict

from textual.app import App, ComposeResult
from textual.containers import ScrollableContainer
from textual.widgets import Header, Footer, Input
import websockets
from websockets.client import WebSocketClientProtocol

from aigent.interfaces.tui.widgets.chat import ChatContainer
from aigent.interfaces.tui.widgets.message import MessageWidget
from aigent.core.schemas import EventType


class AigentApp(App[None]):
    """Aigent TUI Application.

    This is the main Textual application for Aigent's TUI interface.
    It manages WebSocket connections, displays chat messages, and
    handles user input.

    Attributes:
        ws_url: WebSocket URL to connect to.
        session_id: Session ID for the chat session.
        ws: WebSocket connection (set after connection established).
    """

    CSS_PATH = "styles.tcss"
    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+p", "command_palette", "Commands"),
    ]

    def __init__(
        self,
        ws_url: str,
        session_id: str,
        should_lock: bool = False,
        ephemeral: bool = False,
        **kwargs: Any
    ) -> None:
        """Initialize the Aigent TUI application.

        Args:
            ws_url: WebSocket URL to connect to.
            session_id: Session ID for the chat session.
            should_lock: Whether to lock the session. Defaults to False.
            ephemeral: Whether session should be ephemeral. Defaults to False.
            **kwargs: Additional keyword arguments passed to App.
        """
        super().__init__(**kwargs)
        self.ws_url = ws_url
        self.session_id = session_id
        self.should_lock = should_lock
        self.ephemeral = ephemeral
        self.ws: Optional[WebSocketClientProtocol] = None
        self._listener_task: Optional[asyncio.Task[None]] = None
        self._current_message: Optional[MessageWidget] = None

    def compose(self) -> ComposeResult:
        """Compose the UI layout.

        Yields:
            UI components for the application.
        """
        yield Header()
        yield ChatContainer(id="chat")
        yield Input(placeholder="Type a message...", id="input")
        yield Footer()

    async def on_mount(self) -> None:
        """Handle mount event.

        This is called when the app is mounted. It connects to the
        WebSocket server and starts the listener task.
        """
        # Get references to widgets
        chat = self.query_one("#chat", ChatContainer)
        input_widget = self.query_one("#input", Input)

        try:
            # Connect to WebSocket
            self.ws = await websockets.connect(self.ws_url)

            # Send lock request if needed
            if self.should_lock:
                lock_msg = json.dumps({"type": "lock_session"})
                await self.ws.send(lock_msg)

            # Send ephemeral flag if set
            if self.ephemeral:
                ephemeral_msg = json.dumps({"type": "set_ephemeral", "ephemeral": True})
                await self.ws.send(ephemeral_msg)

            # Start listener task
            self._listener_task = asyncio.create_task(self._ws_listener())

            # Focus input
            input_widget.focus()

            # Show connection message
            chat.add_message("Connected to Aigent Server.", role="system")

        except Exception as e:
            chat.add_message(f"Error connecting to server: {e}", role="system")
            sys.stderr.write(f"Connection error: {e}\n")

    async def on_unmount(self) -> None:
        """Handle unmount event.

        This is called when the app is being shut down. It cleans up
        the WebSocket connection and listener task.
        """
        # Cancel listener task
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        # Close WebSocket
        if self.ws:
            await self.ws.close()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission.

        This is called when the user submits input by pressing Enter.

        Args:
            event: The input submission event.
        """
        user_input = event.value.strip()
        if not user_input:
            return

        # Get references to widgets
        chat = self.query_one("#chat", ChatContainer)
        input_widget = self.query_one("#input", Input)

        # Add user message to chat
        chat.add_message(user_input, role="user")

        # Clear input
        input_widget.value = ""

        # Send message via WebSocket
        if self.ws:
            try:
                await self.ws.send(user_input)
            except Exception as e:
                chat.add_message(f"Error sending message: {e}", role="system")

    async def _ws_listener(self) -> None:
        """Listen for WebSocket events and display them.

        This coroutine runs in the background, receiving events from
        the server and updating the chat display accordingly.
        """
        if not self.ws:
            return

        chat = self.query_one("#chat", ChatContainer)

        try:
            async for message in self.ws:
                data: Dict[str, Any] = json.loads(message)
                event_type: str = data.get("type", "")
                content: str = data.get("content", "")
                metadata: Dict[str, Any] = data.get("metadata", {})

                if event_type == EventType.TOKEN:
                    # Stream tokens to current message
                    if self._current_message is None:
                        # Start new assistant message
                        self._current_message = chat.add_message("", role="assistant")

                    # Append token to current message
                    chat.append_to_last(content)

                elif event_type == EventType.FINISH:
                    # End of assistant message
                    self._current_message = None

                elif event_type == EventType.USER_INPUT:
                    # Another user sent a message
                    user_id = metadata.get("user_id", "unknown")
                    chat.add_message(f"[{user_id}] {content}", role="user")

                elif event_type == EventType.SYSTEM:
                    chat.add_message(content, role="system")

                elif event_type == EventType.ERROR:
                    chat.add_message(f"Error: {content}", role="system")

                elif event_type == EventType.TOOL_START:
                    tool_name = content.replace("Calling tool: ", "")
                    input_args = metadata.get("input", {})
                    formatted_args = ", ".join([
                        f"{k}={repr(v)}" for k, v in input_args.items()
                    ])
                    if len(formatted_args) > 100:
                        formatted_args = formatted_args[:100] + "..."
                    chat.add_message(
                        f"🛠  {tool_name}({formatted_args})",
                        role="system"
                    )

                elif event_type == EventType.TOOL_END:
                    tool_content = content
                    if len(tool_content) > 500:
                        tool_content = tool_content[:500] + "..."
                    chat.add_message(f"   {tool_content}", role="system")

                elif event_type == EventType.HISTORY_CONTENT:
                    chat.add_message(content, role="assistant")

        except websockets.ConnectionClosed:
            chat.add_message("Connection to server lost.", role="system")
        except asyncio.CancelledError:
            # Clean shutdown
            pass
        except Exception as e:
            chat.add_message(f"Error in listener: {e}", role="system")

    def action_command_palette(self) -> None:
        """Show command palette.

        This action is bound to Ctrl+P. Currently not implemented,
        reserved for future use.
        """
        # TODO: Implement command palette in Phase 5
        pass

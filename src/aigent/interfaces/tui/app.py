"""Main TUI application for Aigent.

This module implements the Textual-based TUI application for Aigent,
including WebSocket connection handling, message display, and user input.
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Optional, Any, Dict, List
from functools import partial

from textual.app import App, ComposeResult
from textual.command import Hit, Hits, Provider
from textual.containers import ScrollableContainer
from textual.widgets import Header, Footer, Input
import websockets
from websockets.client import WebSocketClientProtocol

from aigent.interfaces.tui.widgets.chat import ChatContainer
from aigent.interfaces.tui.widgets.message import MessageWidget
from aigent.core.schemas import EventType


class AigentCommands(Provider):
    """Command palette provider for Aigent.

    Provides searchable commands for the command palette (Ctrl+P).
    """

    async def search(self, query: str) -> Hits:
        """Search for commands matching query.

        Args:
            query: The search query string.

        Yields:
            Matching command hits with scores.
        """
        matcher = self.matcher(query)

        commands = [
            ("Clear Chat", "clear_chat", "Clear all messages from chat"),
            ("Toggle Lock", "toggle_lock", "Lock/unlock session"),
            ("Exit", "quit", "Exit the application"),
        ]

        for name, action, description in commands:
            score = matcher.match(name)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(name),
                    partial(self.app.action, action),
                    help=description,
                )


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
    COMMANDS = {AigentCommands}
    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+p", "command_palette", "Commands"),
        ("ctrl+l", "clear_chat", "Clear"),
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

        # Token batching state for anti-epilepsy streaming
        self._token_buffer: List[str] = []
        self._last_ui_update: float = 0.0
        self._update_interval: float = 0.016  # ~60fps max (16ms)
        self._pending_update: bool = False
        self._flush_task: Optional[asyncio.Task[None]] = None

    def compose(self) -> ComposeResult:
        """Compose the UI layout.

        Yields:
            UI components for the application.
        """
        yield Header()
        yield ChatContainer(id="chat")
        yield Input(placeholder="Type a message...", id="input")
        yield Footer()

    @property
    def sub_title(self) -> str:
        """Get the subtitle for the header with session info.

        Returns:
            Formatted subtitle string with session ID and lock status.
        """
        lock_status = " [locked]" if self.should_lock else ""
        ephemeral_status = " [ephemeral]" if self.ephemeral else ""
        session_short = self.session_id[:12] if len(self.session_id) > 12 else self.session_id
        return f"Session: {session_short}{lock_status}{ephemeral_status}"

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

    async def _process_token(self, token: str) -> None:
        """Buffer tokens and batch UI updates for smooth streaming.

        This method implements token batching to prevent epileptic-inducing
        rapid redraws. Tokens are buffered and flushed to the UI at a
        maximum rate of ~60fps.

        Args:
            token: The token to add to the buffer.
        """
        self._token_buffer.append(token)

        now = time.monotonic()
        time_since_last_update = now - self._last_ui_update

        # If enough time has passed since last update, flush immediately
        if time_since_last_update >= self._update_interval:
            await self._flush_tokens()
        # Otherwise, schedule a flush if not already pending
        elif not self._pending_update:
            self._pending_update = True
            delay = self._update_interval - time_since_last_update
            self._flush_task = asyncio.create_task(
                self._schedule_flush(delay)
            )

    async def _schedule_flush(self, delay: float) -> None:
        """Schedule a token flush after a delay.

        Args:
            delay: Time in seconds to wait before flushing.
        """
        await asyncio.sleep(delay)
        await self._flush_tokens()

    async def _flush_tokens(self) -> None:
        """Flush buffered tokens to the UI.

        This method takes all buffered tokens and appends them to the
        current message widget in one operation, minimizing redraws.
        """
        if not self._token_buffer:
            return

        content = ''.join(self._token_buffer)
        self._token_buffer.clear()
        self._pending_update = False
        self._last_ui_update = time.monotonic()

        # Cancel any pending flush task
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        self._flush_task = None

        # Append to current message using the chat container's method
        chat = self.query_one("#chat", ChatContainer)
        if self._current_message is not None:
            chat.append_to_current(content)

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
                    # Stream tokens to current message with batching
                    if self._current_message is None:
                        # Start new assistant message
                        self._current_message = chat.start_message(role="assistant")

                    # Use batched token processing (anti-epilepsy)
                    await self._process_token(content)

                elif event_type == EventType.FINISH:
                    # Flush any remaining tokens before marking complete
                    await self._flush_tokens()
                    # End of assistant message
                    chat.finish_message()
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

    def action_clear_chat(self) -> None:
        """Clear all messages from chat.

        This action is bound to Ctrl+L and is also available from
        the command palette.
        """
        chat = self.query_one("#chat", ChatContainer)
        chat.remove_children()
        chat.add_message("Chat cleared.", role="system")

    async def action_toggle_lock(self) -> None:
        """Toggle session lock.

        This action is available from the command palette. It sends
        a lock or unlock request to the server.
        """
        if not self.ws:
            return

        try:
            if self.should_lock:
                # Unlock the session
                unlock_msg = json.dumps({"type": "unlock_session"})
                await self.ws.send(unlock_msg)
                self.should_lock = False
                chat = self.query_one("#chat", ChatContainer)
                chat.add_message("Session unlocked.", role="system")
            else:
                # Lock the session
                lock_msg = json.dumps({"type": "lock_session"})
                await self.ws.send(lock_msg)
                self.should_lock = True
                chat = self.query_one("#chat", ChatContainer)
                chat.add_message("Session locked.", role="system")

            # Update the header to reflect new lock status
            header = self.query_one(Header)
            header.refresh()
        except Exception as e:
            chat = self.query_one("#chat", ChatContainer)
            chat.add_message(f"Error toggling lock: {e}", role="system")

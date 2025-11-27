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
from textual.suggester import Suggester
from textual.widgets import Header, Footer, Input
import websockets
from websockets.client import WebSocketClientProtocol

from aigent.interfaces.tui.widgets.chat import ChatContainer
from aigent.interfaces.tui.widgets.message import MessageWidget
from aigent.interfaces.tui.widgets.approval_dialog import ApprovalDialog
from aigent.core.schemas import EventType
from aigent.interfaces.commands import get_command_names


class SlashCommandSuggester(Suggester):
    """Suggester for slash command autocomplete.

    This suggester provides autocomplete functionality for slash commands
    in the TUI input widget. It suggests commands from the command registry
    when the user types a slash followed by a prefix.
    """

    def __init__(self) -> None:
        """Initialize the suggester with known commands."""
        super().__init__()
        # Get all known commands from the registry
        self.commands: List[str] = sorted(get_command_names())

    async def get_suggestion(self, value: str) -> Optional[str]:
        """Get autocomplete suggestion for the given input value.

        Args:
            value: The current input value from the user.

        Returns:
            A matching command string if found, None otherwise.
        """
        # Only suggest for slash commands
        if not value.startswith("/"):
            return None

        # Find matching commands
        for cmd in self.commands:
            # Suggest if cmd starts with value and is not identical
            if cmd.startswith(value) and cmd != value:
                return cmd

        # No suggestion for complete commands or unknown prefixes
        return None


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
        client_id: Optional[str] = None,
        cursor_blink: bool = False,
        **kwargs: Any
    ) -> None:
        """Initialize the Aigent TUI application.

        Args:
            ws_url: WebSocket URL to connect to.
            session_id: Session ID for the chat session.
            should_lock: Whether to lock the session. Defaults to False.
            ephemeral: Whether session should be ephemeral. Defaults to False.
            client_id: Client ID for filtering own messages. If None, will try to
                extract from ws_url query parameters. Defaults to None.
            cursor_blink: Whether the input cursor should blink. Defaults to False.
            **kwargs: Additional keyword arguments passed to App.
        """
        super().__init__(**kwargs)
        self.ws_url = ws_url
        self.session_id = session_id
        self.should_lock = should_lock
        self.ephemeral = ephemeral
        self.cursor_blink = cursor_blink

        # Extract or generate client_id
        if client_id is None:
            # Try to extract from ws_url query parameters
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(ws_url)
            query_params = parse_qs(parsed.query)
            client_id = query_params.get("user_id", [None])[0]

            # If still None, generate a deterministic ID based on session
            # This is primarily for testing scenarios
            if client_id is None:
                import uuid
                client_id = f"tui-{uuid.uuid4().hex[:8]}"

        self.client_id = client_id
        self.ws: Optional[WebSocketClientProtocol] = None
        self._listener_task: Optional[asyncio.Task[None]] = None
        self._current_message: Optional[MessageWidget] = None
        self._current_approval_dialog: Optional[ApprovalDialog] = None

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
        input_widget = Input(
            placeholder="Type a message...",
            id="input",
            suggester=SlashCommandSuggester()
        )
        input_widget.cursor_blink = self.cursor_blink
        yield input_widget
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

    @sub_title.setter
    def sub_title(self, value: str) -> None:
        """Setter for sub_title (required by Textual's App.__init__).

        Args:
            value: The subtitle value (ignored, we compute it dynamically).
        """
        # Textual's App.__init__ tries to set this, but we compute it dynamically
        # So we just ignore the setter
        pass

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

        # Add user message to chat immediately for responsive UX
        # Note: When the server broadcasts the USER_INPUT event back,
        # _ws_listener() will filter it out to prevent duplication
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
                    # User message broadcast from server
                    user_id = metadata.get("user_id", "unknown")

                    # Filter out our own messages to prevent duplication
                    # (we already added our message locally in on_input_submitted)
                    if self.client_id and user_id == self.client_id:
                        continue

                    # Display messages from other users
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

                elif event_type == EventType.APPROVAL_REQUEST:
                    # Tool permission request
                    tool = metadata.get("tool")
                    args = metadata.get("input")
                    req_id = metadata.get("request_id")
                    await self._show_approval_dialog(tool, args, req_id)

        except websockets.ConnectionClosed:
            chat.add_message("Connection to server lost.", role="system")
        except asyncio.CancelledError:
            # Clean shutdown
            pass
        except Exception as e:
            chat.add_message(f"Error in listener: {e}", role="system")

    async def _show_approval_dialog(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        request_id: str
    ) -> None:
        """Show approval dialog for tool execution.

        This method displays a modal dialog asking the user to approve
        or deny a tool execution request.

        Args:
            tool_name: Name of the tool requesting approval.
            tool_input: Input arguments for the tool.
            request_id: Unique identifier for this approval request.
        """
        # Create and show the approval dialog
        dialog = ApprovalDialog(
            tool_name=tool_name,
            tool_input=tool_input,
            request_id=request_id,
            on_decision=self._send_approval_response
        )
        self._current_approval_dialog = dialog
        await self.push_screen(dialog)

    def _send_approval_response(self, request_id: str, decision: str) -> None:
        """Send approval response to server.

        This method sends the user's decision about a tool execution
        request back to the server via WebSocket.

        Args:
            request_id: Unique identifier for the approval request.
            decision: The user's decision (allow/deny/always_tool/always_smart).
        """
        if not self.ws:
            return

        response = {
            "type": "approval_response",
            "request_id": request_id,
            "decision": decision
        }

        # Send the response asynchronously
        # We need to use asyncio.create_task since this might be called from a sync context
        asyncio.create_task(self._async_send_approval(response))

        # Clear the current dialog reference
        self._current_approval_dialog = None

    async def _async_send_approval(self, response: Dict[str, Any]) -> None:
        """Asynchronously send approval response.

        Helper method to send approval response via WebSocket.

        Args:
            response: The approval response dictionary to send.
        """
        if self.ws:
            try:
                await self.ws.send(json.dumps(response))
            except Exception as e:
                chat = self.query_one("#chat", ChatContainer)
                chat.add_message(f"Error sending approval response: {e}", role="system")

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

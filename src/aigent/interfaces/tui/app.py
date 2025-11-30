"""Main TUI application for Aigent.

This module implements the Textual-based TUI application for Aigent.
"""

import asyncio
import json
import sys
import time
from typing import Optional, Any, Dict, List
from functools import partial

from textual.app import App, ComposeResult
from textual.command import Hit, Hits, Provider
from textual.widgets import Header, Footer, Input
from textual.suggester import Suggester
import websockets
from websockets.client import WebSocketClientProtocol

from aigent.interfaces.tui.widgets.chat import ChatContainer
from aigent.interfaces.tui.widgets.message import MessageWidget
from aigent.interfaces.tui.widgets.approval_dialog import ApprovalDialog
from aigent.core.logging import get_logger
from aigent.interfaces.commands import get_command_names
from aigent.interfaces.utils import ensure_server

logger = get_logger(__name__)


class SlashCommandSuggester(Suggester):
    def __init__(self) -> None:
        super().__init__()
        self.commands: List[str] = sorted(get_command_names())

    async def get_suggestion(self, value: str) -> Optional[str]:
        if not value.startswith("/"):
            return None
        for cmd in self.commands:
            if cmd.startswith(value) and cmd != value:
                return cmd
        return None


class AigentCommands(Provider):
    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        commands = [
            ("Clear Chat", "clear_chat", "Clear all messages from chat"),
            ("Exit", "quit", "Exit the application"),
        ]
        for name, action, description in commands:
            score = matcher.match(name)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(name),
                    partial(self.app.action, action),  # type: ignore[attr-defined]
                    help=description,
                )


class AigentApp(App[None]):
    CSS_PATH = "styles.tcss"
    COMMANDS = {AigentCommands}
    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+p", "command_palette", "Commands"),
        ("ctrl+l", "clear_chat", "Clear"),
    ]

    def __init__(self, args: Any, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.args = args
        self.ws_url = (
            f"ws://{args.host}:{args.port}/ws/chat/{args.session or 'tui-session'}?client_type=tui"
        )
        self.ws: Optional[WebSocketClientProtocol] = None
        self._token_buffer: List[str] = []
        self._current_message: Optional[MessageWidget] = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield ChatContainer(id="chat")
        yield Input(placeholder="Type a message...", id="input", suggester=SlashCommandSuggester())
        yield Footer()

    async def on_mount(self) -> None:
        try:
            self.ws = await websockets.connect(self.ws_url)
            asyncio.create_task(self._ws_listener())
            self.query_one("#chat", ChatContainer).add_message(
                "Connected to Aigent.", role="system"
            )
        except Exception as e:
            self.query_one("#chat", ChatContainer).add_message(
                f"Connection Failed: {e}", role="system"
            )

    async def _ws_listener(self) -> None:
        if not self.ws:
            return
        try:
            async for message in self.ws:
                data = json.loads(message)
                event_type = data.get("type")
                content = data.get("content", "")

                chat = self.query_one("#chat", ChatContainer)

                if event_type == "token":
                    if not self._current_message:
                        self._current_message = chat.start_message(role="assistant")
                    self._current_message.append(content)

                elif event_type == "finish":
                    chat.finish_message()
                    self._current_message = None

                elif event_type == "user_input":
                    chat.add_message(content, role="user")

                elif event_type == "tool_end":
                    chat.add_message(f"Tool Output: {content}", role="system")

                elif event_type == "approval_request":
                    meta = data.get("metadata", {})
                    await self.push_screen(
                        ApprovalDialog(
                            tool_name=meta.get("tool"),
                            tool_input=meta.get("input"),
                            request_id=meta.get("request_id"),
                            on_decision=self._send_approval,
                        )
                    )

        except Exception as e:
            logger.error(f"WS Error: {e}")

    def _send_approval(self, request_id: str, decision: str) -> None:
        if self.ws:
            payload = {"type": "approval_response", "request_id": request_id, "decision": decision}
            asyncio.create_task(self.ws.send(json.dumps(payload)))

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if not self.ws:
            return
        val = event.value.strip()
        if val:
            await self.ws.send(val)
            event.input.value = ""

    def action_clear_chat(self) -> None:
        self.query_one("#chat", ChatContainer).remove_children()


async def run_tui_async(args: Any) -> None:
    if not await ensure_server(args.host, args.port):
        return
    app = AigentApp(args)
    await app.run_async()


def run_tui(args: Any) -> Any:
    # Textual's app.run() is async-compatible but best run via run_async if we are already in async mode?
    # CLI calls asyncio.run(run_tui(args)).
    # So run_tui should be async.
    # Wait, cli.py calls asyncio.run(run_tui(args)).
    # So run_tui must be a coroutine.
    return run_tui_async(args)

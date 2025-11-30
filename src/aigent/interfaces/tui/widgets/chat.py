"""Chat container widget for TUI interface.

This module provides a scrollable container for displaying chat messages
in the TUI interface with support for message streaming and history.
"""

from typing import Literal, Optional
from textual.containers import ScrollableContainer
from aigent.interfaces.tui.widgets.message import MessageWidget, RoleType


class ChatContainer(ScrollableContainer):
    """Container for chat messages."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._current_streaming_message: Optional[MessageWidget] = None

    def add_message(self, content: str, role: RoleType = "user") -> MessageWidget:
        """Add a new message to the chat."""
        msg = MessageWidget(content, role=role)
        self.mount(msg)
        self.scroll_end(animate=False)
        return msg

    def start_message(self, role: RoleType = "assistant") -> MessageWidget:
        """Start a new streaming message."""
        msg = MessageWidget("", role=role)
        self.mount(msg)
        self._current_streaming_message = msg
        self.scroll_end(animate=False)
        return msg

    def append_to_current(self, content: str) -> None:
        """Append content to the current streaming message."""
        if self._current_streaming_message:
            self._current_streaming_message.append(content)
            self.scroll_end(animate=False)

    def finish_message(self) -> None:
        """Mark the current streaming message as complete."""
        self._current_streaming_message = None

"""Chat container widget for TUI interface.

This module provides a scrollable container for displaying chat messages
in the TUI interface with support for message streaming and history.
"""

from typing import Literal, Optional
from textual.containers import ScrollableContainer
from aigent.interfaces.tui.widgets.message import MessageWidget, RoleType


class ChatContainer(ScrollableContainer):
    """Container for chat messages.

    This widget provides a scrollable container for displaying chat messages
    with methods for adding new messages and appending to existing ones for
    streaming support.

    Attributes:
        _current_streaming_message: Reference to the message currently being
            streamed, or None if no streaming is in progress.
    """

    def __init__(self, **kwargs: object) -> None:
        """Initialize the chat container.

        Args:
            **kwargs: Additional keyword arguments passed to ScrollableContainer.
        """
        super().__init__(**kwargs)
        self._current_streaming_message: Optional[MessageWidget] = None

    def add_message(
        self,
        content: str,
        role: RoleType = "user"
    ) -> MessageWidget:
        """Add a new message to the chat.

        Creates a new MessageWidget and adds it to the container,
        then scrolls to the end to show the new message.

        Args:
            content: The text content of the message.
            role: The role of the message sender. Defaults to "user".

        Returns:
            The newly created MessageWidget.
        """
        msg = MessageWidget(content, role=role)
        self.mount(msg)
        self.scroll_end(animate=False)  # No animation = faster
        return msg

    def start_message(self, role: RoleType = "assistant") -> MessageWidget:
        """Start a new streaming message.

        Creates a new empty message widget and marks it as the current
        streaming message. Subsequent calls to append_to_current() will
        append to this message.

        Args:
            role: The role of the message sender. Defaults to "assistant".

        Returns:
            The newly created MessageWidget.
        """
        msg = MessageWidget("", role=role)
        self.mount(msg)
        self._current_streaming_message = msg
        self.scroll_end(animate=False)  # No animation = faster
        return msg

    def append_to_current(self, content: str) -> None:
        """Append content to the current streaming message.

        This method is optimized for streaming, appending text without
        triggering full redraws. If no streaming message is active, this
        method does nothing.

        Args:
            content: The text content to append.
        """
        if self._current_streaming_message:
            self._current_streaming_message.append(content)
            # Only scroll if we're near the bottom to avoid jarring scrolls
            # when user is reading earlier messages
            self.scroll_end(animate=False)

    def finish_message(self) -> None:
        """Mark the current streaming message as complete.

        Clears the reference to the current streaming message.
        """
        self._current_streaming_message = None

    def append_to_last(self, content: str) -> None:
        """Append content to the last message.

        This is useful for streaming messages where tokens arrive
        incrementally. Appends the content to the most recent message
        in the container.

        DEPRECATED: Use start_message() and append_to_current() instead
        for better streaming support.

        Args:
            content: The text content to append.
        """
        if self.children:
            last = self.children[-1]
            if isinstance(last, MessageWidget):
                # Get current content and append new content
                current = str(last.renderable)
                last.update(current + content)
                self.scroll_end(animate=False)

"""Chat container widget for TUI interface.

This module provides a scrollable container for displaying chat messages
in the TUI interface with support for message streaming and history.
"""

from typing import Literal
from textual.containers import ScrollableContainer
from aigent.interfaces.tui.widgets.message import MessageWidget, RoleType


class ChatContainer(ScrollableContainer):
    """Container for chat messages.

    This widget provides a scrollable container for displaying chat messages
    with methods for adding new messages and appending to existing ones for
    streaming support.
    """

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
        self.scroll_end()
        return msg

    def append_to_last(self, content: str) -> None:
        """Append content to the last message.

        This is useful for streaming messages where tokens arrive
        incrementally. Appends the content to the most recent message
        in the container.

        Args:
            content: The text content to append.
        """
        if self.children:
            last = self.children[-1]
            if isinstance(last, MessageWidget):
                # Get current content and append new content
                current = str(last.renderable)
                last.update(current + content)
                self.scroll_end()

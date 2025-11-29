"""Message widget for TUI chat interface.

This module provides a widget for displaying individual messages in the chat
with support for different message roles (user, assistant, system) and
streaming append-only updates.
"""

from typing import Literal
from textual.widgets import Static
from textual.reactive import reactive


RoleType = Literal["user", "assistant", "system"]


class MessageWidget(Static):
    """A single message in the chat.

    This widget displays a single message with appropriate styling based
    on the role of the sender. It supports append-only streaming updates
    to prevent full redraws during token streaming.

    Attributes:
        role: The role of the message sender (user, assistant, or system).
        _content: Internal storage for the message content.
    """

    role: RoleType = reactive("user")  # type: ignore

    def __init__(
        self,
        content: str = "",
        role: RoleType = "user",
        **kwargs: object
    ) -> None:
        """Initialize a message widget.

        Args:
            content: The text content of the message. Defaults to empty string.
            role: The role of the message sender. Defaults to "user".
            **kwargs: Additional keyword arguments passed to Static.
        """
        super().__init__(content, **kwargs)
        self.role = role
        self._content = content

    def append(self, text: str) -> None:
        """Append text to the message without triggering a full redraw.

        This method is optimized for streaming updates. It appends text
        to the internal content buffer and uses update() which is optimized
        for text changes in Textual.

        Args:
            text: The text to append to the message.
        """
        self._content += text
        self.update(self._content)

    @property
    def text(self) -> str:
        """Get the current text content of the message."""
        return self._content

    def watch_role(self, role: RoleType) -> None:
        """Update CSS classes when role changes."""
        self.set_class(role == "user", "user-message")
        self.set_class(role == "assistant", "assistant-message")
        self.set_class(role == "system", "system-message")

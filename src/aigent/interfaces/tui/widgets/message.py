"""Message widget for TUI chat interface.

This module provides a widget for displaying individual messages in the chat
with support for different message roles (user, assistant, system).
"""

from typing import Literal
from textual.widgets import Static
from textual.reactive import reactive


RoleType = Literal["user", "assistant", "system"]


class MessageWidget(Static):
    """A single message in the chat.

    This widget displays a single message with appropriate styling based
    on the role of the sender.

    Attributes:
        role: The role of the message sender (user, assistant, or system).
    """

    role: RoleType = reactive("user")  # type: ignore

    def __init__(
        self,
        content: str,
        role: RoleType = "user",
        **kwargs: object
    ) -> None:
        """Initialize a message widget.

        Args:
            content: The text content of the message.
            role: The role of the message sender. Defaults to "user".
            **kwargs: Additional keyword arguments passed to Static.
        """
        super().__init__(content, **kwargs)
        self.role = role

    def watch_role(self, role: RoleType) -> None:
        """Update CSS classes when role changes.

        This method is called automatically by Textual's reactive system
        when the role attribute changes.

        Args:
            role: The new role value.
        """
        self.set_class(role == "user", "user-message")
        self.set_class(role == "assistant", "assistant-message")
        self.set_class(role == "system", "system-message")

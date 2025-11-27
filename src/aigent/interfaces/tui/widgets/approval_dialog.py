"""Approval dialog widget for tool execution permissions.

This module provides a modal dialog for requesting user approval
before executing potentially sensitive tool operations.
"""

import json
from typing import Any, Dict, Optional, Callable
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class ApprovalDialog(ModalScreen[str]):
    """Modal dialog for tool execution approval.

    This dialog displays information about a tool that is requesting
    permission to execute, and provides buttons for the user to approve
    or deny the request.

    Attributes:
        tool_name: Name of the tool requesting approval.
        tool_input: Input arguments for the tool.
        request_id: Unique identifier for this approval request.
        on_decision: Callback function called with the decision.
    """

    CSS = """
    ApprovalDialog {
        align: center middle;
    }

    #approval-dialog-container {
        width: 80;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }

    #approval-header {
        width: 100%;
        text-align: center;
        background: $primary;
        color: $text;
        padding: 1;
        margin-bottom: 1;
    }

    #approval-content {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }

    .approval-label {
        margin: 0 0 1 0;
    }

    #approval-buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }

    .approval-button {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        request_id: str,
        on_decision: Callable[[str, str], None],
        **kwargs: Any
    ) -> None:
        """Initialize the approval dialog.

        Args:
            tool_name: Name of the tool requesting approval.
            tool_input: Input arguments for the tool.
            request_id: Unique identifier for this approval request.
            on_decision: Callback function called with (request_id, decision).
            **kwargs: Additional keyword arguments passed to ModalScreen.
        """
        super().__init__(**kwargs)
        self.tool_name = tool_name
        self.tool_input = tool_input
        self.request_id = request_id
        self.on_decision = on_decision

    def compose(self) -> ComposeResult:
        """Compose the dialog UI.

        Yields:
            UI components for the approval dialog.
        """
        # Format tool input for display
        if isinstance(self.tool_input, dict):
            formatted_input = json.dumps(self.tool_input, indent=2)
        else:
            formatted_input = str(self.tool_input)

        # Truncate if too long
        if len(formatted_input) > 500:
            formatted_input = formatted_input[:500] + "\n..."

        with Vertical(id="approval-dialog-container"):
            yield Label("Tool Permission Request", id="approval-header")

            with Vertical(id="approval-content"):
                yield Label(
                    f"Tool: {self.tool_name}",
                    classes="approval-label"
                )
                yield Static(
                    f"Arguments:\n{formatted_input}",
                    classes="approval-label"
                )

            with Horizontal(id="approval-buttons"):
                yield Button(
                    "Allow",
                    variant="success",
                    id="allow-button",
                    classes="approval-button"
                )
                yield Button(
                    "Deny",
                    variant="error",
                    id="deny-button",
                    classes="approval-button"
                )
                yield Button(
                    "Always Allow Tool",
                    variant="primary",
                    id="always-allow-button",
                    classes="approval-button"
                )
                yield Button(
                    "Smart Allow",
                    variant="primary",
                    id="smart-allow-button",
                    classes="approval-button"
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events.

        Maps button IDs to approval decisions and calls the decision callback.

        Args:
            event: The button press event.
        """
        button_id = event.button.id
        decision = "deny"  # Default to deny for safety

        if button_id == "allow-button":
            decision = "allow"
        elif button_id == "deny-button":
            decision = "deny"
        elif button_id == "always-allow-button":
            decision = "always_tool"
        elif button_id == "smart-allow-button":
            decision = "always_smart"

        # Call the decision callback
        self.on_decision(self.request_id, decision)

        # Dismiss the dialog
        self.dismiss(decision)

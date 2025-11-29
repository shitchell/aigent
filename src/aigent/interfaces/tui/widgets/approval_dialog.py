"""Approval dialog widget for tool execution permissions."""

import json
from typing import Any, Dict, Callable
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class ApprovalDialog(ModalScreen[str]):
    """Modal dialog for tool execution approval."""

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
        super().__init__(**kwargs)
        self.tool_name = tool_name
        self.tool_input = tool_input
        self.request_id = request_id
        self.on_decision = on_decision

    def compose(self) -> ComposeResult:
        if isinstance(self.tool_input, dict):
            formatted_input = json.dumps(self.tool_input, indent=2)
        else:
            formatted_input = str(self.tool_input)

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
                yield Button("Allow", variant="success", id="allow-button", classes="approval-button")
                yield Button("Deny", variant="error", id="deny-button", classes="approval-button")
                yield Button("Always", variant="primary", id="always-allow-button", classes="approval-button")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        decision = "deny"

        if button_id == "allow-button":
            decision = "allow"
        elif button_id == "deny-button":
            decision = "deny"
        elif button_id == "always-allow-button":
            decision = "always_tool"

        self.on_decision(self.request_id, decision)
        self.dismiss(decision)

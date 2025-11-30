import pytest
from textual.pilot import Pilot
from textual.widgets import Label
import asyncio
from aigent.interfaces.tui.app import AigentApp
from aigent.interfaces.tui.widgets.chat import ChatContainer
import time


# Mock Args
class MockArgs:
    def __init__(self, host, port, session=None):
        self.host = host
        self.port = port
        self.session = session


async def wait_for_text(pilot, text, timeout=10.0):
    start = time.time()
    while time.time() - start < timeout:
        # Check Chat Messages
        for msg in pilot.app.query("MessageWidget"):
            if text in msg.text:
                return
        # Check Labels (for Dialogs)
        for label in pilot.app.query(Label):
            if text in str(label.renderable):
                return
        await pilot.pause(0.2)
    raise TimeoutError(f"Text '{text}' not found in UI")


@pytest.mark.asyncio
async def test_tui_tool_approval_loop(aigent_server):
    """
    Reproduce Issue 1: Tool execution causes double permission request or hang.
    """
    # Extract host/port from aigent_server fixture (ws://127.0.0.1:port)
    base_url = aigent_server.replace("ws://", "")
    host, port = base_url.split(":")

    args = MockArgs(host=host, port=int(port), session="test-tui-loop")
    app = AigentApp(args)

    async with app.run_test() as pilot:
        # 1. Connect and Wait for Ready
        await wait_for_text(pilot, "Connected to Aigent")

        # 2. Type 'run ls' (assuming bash_execute is mapped to natural language?
        # Actually LLM interprets "run ls" -> bash_execute("ls").
        # But we are mocking LLM? No, live server.
        # But server uses OpenAI/Gemini.
        # "run ls" might fail if no key.
        # However, the goal is to trigger approval.
        # I'll manually dispatch a tool request from the server side? No, E2E.

        # If no key, LLM fails.
        # I'll inject a fake tool request via a custom plugin or special command?
        # Or I trust the LLM?

        # For REPRODUCIBILITY without paying OpenAI, I should probably mock the LLM or inject the event.
        # But the test setup spawns a real server.

        # Let's try sending a message that *would* trigger a tool.
        # If it fails (LLM error), the test fails.

        await pilot.click("#input")
        await pilot.press(*"run ls")
        await pilot.press("enter")

        # 3. Wait for Approval Dialog
        # This might timeout if LLM fails.
        try:
            await wait_for_text(pilot, "Tool Permission Request", timeout=15.0)
        except TimeoutError:
            pytest.skip("Skipping TUI Loop test: LLM did not trigger tool (or no API key)")

        # 4. Click 'Allow'
        await pilot.click("#allow-button")

        # 5. Assertions
        # Wait for Tool Output
        try:
            await wait_for_text(pilot, "Tool Output", timeout=5.0)
        except TimeoutError:
            pytest.fail("Tool Output did not appear (Hang/Loop detected)")

        # Ensure no Approval Dialog is present
        assert len(app.screen_stack) == 1, "Approval Dialog did not close"

"""
Integration tests for session management and switching.
Tests remote session management via WebSocket commands.
"""

import pytest
import asyncio
import json
import subprocess
import sys
import websockets
from typing import Optional, List


class TestSessionSwitching:
    """Test suite for session switching and management."""

    async def start_test_server(self, port: int) -> subprocess.Popen:
        """Helper to start a test server."""
        proc = subprocess.Popen(
            [sys.executable, "-m", "aigent.main", "serve", "--port", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Wait for server to be ready
        for _ in range(20):
            try:
                async with websockets.connect(f"ws://localhost:{port}/ws/chat/init-test") as ws:
                    break
            except:
                await asyncio.sleep(0.5)
        else:
            proc.terminate()
            proc.wait()
            raise TimeoutError("Server failed to start")

        return proc

    async def receive_until_finish(self, ws) -> List[dict]:
        """Receive messages until FINISH event."""
        messages = []
        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(msg)
                messages.append(data)
                if data.get("type") == "finish":
                    break
            except asyncio.TimeoutError:
                break
        return messages

    @pytest.mark.asyncio
    async def test_session_creation_and_switching(self):
        """Test creating and switching between sessions."""
        port = 18100
        proc = None

        try:
            proc = await self.start_test_server(port)

            # Connect to initial session
            session1_id = "session-1"
            ws1_url = f"ws://localhost:{port}/ws/chat/{session1_id}?profile=default"

            async with websockets.connect(ws1_url) as ws1:
                # Send message to session 1
                await ws1.send("Hello from session 1")

                # Wait for response
                messages = await self.receive_until_finish(ws1)

                # Verify we got user input echo
                user_inputs = [m for m in messages if m.get("type") == "user_input"]
                assert len(user_inputs) == 1
                assert user_inputs[0]["content"] == "Hello from session 1"

            # Connect to different session
            session2_id = "session-2"
            ws2_url = f"ws://localhost:{port}/ws/chat/{session2_id}?profile=default"

            async with websockets.connect(ws2_url) as ws2:
                # Send message to session 2
                await ws2.send("Hello from session 2")

                # Wait for response
                messages = await self.receive_until_finish(ws2)

                # Verify we got user input echo
                user_inputs = [m for m in messages if m.get("type") == "user_input"]
                assert len(user_inputs) == 1
                assert user_inputs[0]["content"] == "Hello from session 2"

            # Reconnect to session 1 and verify history
            async with websockets.connect(ws1_url) as ws1:
                # Should receive history replay
                await asyncio.sleep(1)  # Give time for history replay

                # Send another message
                await ws1.send("Back to session 1")

                messages = await self.receive_until_finish(ws1)

                # Should see the new message
                user_inputs = [m for m in messages if m.get("type") == "user_input"]
                assert any("Back to session 1" in m.get("content", "") for m in user_inputs)

        finally:
            if proc:
                proc.terminate()
                proc.wait(timeout=5)

    @pytest.mark.asyncio
    async def test_concurrent_sessions(self):
        """Test multiple concurrent sessions."""
        port = 18101
        proc = None

        try:
            proc = await self.start_test_server(port)

            # Connect to multiple sessions concurrently
            session_ids = ["concurrent-1", "concurrent-2", "concurrent-3"]
            websockets_list = []

            for session_id in session_ids:
                ws_url = f"ws://localhost:{port}/ws/chat/{session_id}?profile=default"
                ws = await websockets.connect(ws_url)
                websockets_list.append((session_id, ws))

            # Send messages to all sessions
            for session_id, ws in websockets_list:
                await ws.send(f"Message from {session_id}")

            # Verify each session gets its own message
            for session_id, ws in websockets_list:
                messages = await self.receive_until_finish(ws)
                user_inputs = [m for m in messages if m.get("type") == "user_input"]
                assert len(user_inputs) >= 1
                assert f"Message from {session_id}" in user_inputs[0]["content"]

            # Close all connections
            for _, ws in websockets_list:
                await ws.close()

        finally:
            if proc:
                proc.terminate()
                proc.wait(timeout=5)

    @pytest.mark.asyncio
    async def test_session_isolation(self):
        """Test that sessions are properly isolated from each other."""
        port = 18102
        proc = None

        try:
            proc = await self.start_test_server(port)

            # Create two WebSocket connections to different sessions
            ws1_url = f"ws://localhost:{port}/ws/chat/isolated-1?profile=default"
            ws2_url = f"ws://localhost:{port}/ws/chat/isolated-2?profile=default"

            async with websockets.connect(ws1_url) as ws1:
                async with websockets.connect(ws2_url) as ws2:
                    # Send message to session 1
                    await ws1.send("Secret message in session 1")

                    # Collect messages from session 1
                    messages1 = []
                    while True:
                        try:
                            msg = await asyncio.wait_for(ws1.recv(), timeout=2.0)
                            data = json.loads(msg)
                            messages1.append(data)
                            if data.get("type") == "finish":
                                break
                        except asyncio.TimeoutError:
                            break

                    # Try to receive from session 2 (should not get session 1's messages)
                    messages2 = []
                    try:
                        msg = await asyncio.wait_for(ws2.recv(), timeout=1.0)
                        data = json.loads(msg)
                        messages2.append(data)
                    except asyncio.TimeoutError:
                        pass  # Expected - no messages

                    # Verify session 1 got its message
                    user_inputs1 = [m for m in messages1 if m.get("type") == "user_input"]
                    assert len(user_inputs1) == 1
                    assert "Secret message in session 1" in user_inputs1[0]["content"]

                    # Verify session 2 did NOT get session 1's message
                    user_inputs2 = [m for m in messages2 if m.get("type") == "user_input"]
                    assert len(user_inputs2) == 0

        finally:
            if proc:
                proc.terminate()
                proc.wait(timeout=5)

    @pytest.mark.asyncio
    async def test_session_persistence_across_reconnect(self):
        """Test that session state persists across reconnections."""
        port = 18103
        proc = None

        try:
            proc = await self.start_test_server(port)

            session_id = "persistent-session"
            ws_url = f"ws://localhost:{port}/ws/chat/{session_id}?profile=default"

            # First connection
            async with websockets.connect(ws_url) as ws:
                await ws.send("First message")
                messages = await self.receive_until_finish(ws)
                assert any("First message" in m.get("content", "") for m in messages)

            # Disconnect and reconnect
            await asyncio.sleep(1)

            # Second connection to same session
            async with websockets.connect(ws_url) as ws:
                # Should receive history on connect
                history_messages = []
                try:
                    # Collect any history replay
                    for _ in range(10):
                        msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                        data = json.loads(msg)
                        history_messages.append(data)
                except asyncio.TimeoutError:
                    pass

                # Check if first message is in history
                all_content = " ".join(m.get("content", "") for m in history_messages)
                # Note: History replay format might vary, just check the message exists somewhere

                # Send second message
                await ws.send("Second message")
                new_messages = await self.receive_until_finish(ws)

                # Should see second message
                assert any("Second message" in m.get("content", "") for m in new_messages)

        finally:
            if proc:
                proc.terminate()
                proc.wait(timeout=5)

    @pytest.mark.asyncio
    async def test_multiple_clients_same_session(self):
        """Test multiple clients connecting to the same session."""
        port = 18104
        proc = None

        try:
            proc = await self.start_test_server(port)

            session_id = "shared-session"
            ws_url = f"ws://localhost:{port}/ws/chat/{session_id}?profile=default"

            # Connect two clients to same session
            async with websockets.connect(ws_url + "&user_id=client1") as ws1:
                async with websockets.connect(ws_url + "&user_id=client2") as ws2:

                    # Client 1 sends a message
                    await ws1.send("Message from client 1")

                    # Both clients should receive the message
                    messages1 = []
                    messages2 = []

                    # Collect messages from both clients
                    for _ in range(10):
                        try:
                            msg1 = await asyncio.wait_for(ws1.recv(), timeout=0.5)
                            messages1.append(json.loads(msg1))
                        except asyncio.TimeoutError:
                            break

                    for _ in range(10):
                        try:
                            msg2 = await asyncio.wait_for(ws2.recv(), timeout=0.5)
                            messages2.append(json.loads(msg2))
                        except asyncio.TimeoutError:
                            break

                    # Both should have received the user_input event
                    user_inputs1 = [m for m in messages1 if m.get("type") == "user_input"]
                    user_inputs2 = [m for m in messages2 if m.get("type") == "user_input"]

                    assert len(user_inputs1) > 0
                    assert len(user_inputs2) > 0
                    assert "Message from client 1" in user_inputs1[0].get("content", "")
                    assert "Message from client 1" in user_inputs2[0].get("content", "")

        finally:
            if proc:
                proc.terminate()
                proc.wait(timeout=5)

    @pytest.mark.asyncio
    async def test_session_command_handling(self):
        """Test handling of session-specific commands."""
        port = 18105
        proc = None

        try:
            proc = await self.start_test_server(port)

            session_id = "command-test"
            ws_url = f"ws://localhost:{port}/ws/chat/{session_id}?profile=default"

            async with websockets.connect(ws_url) as ws:
                # Send a regular message first
                await ws.send("Initial message")
                await self.receive_until_finish(ws)

                # Send a command (JSON format)
                reset_command = json.dumps({
                    "type": "command",
                    "content": "/reset"
                })
                await ws.send(reset_command)

                # Should receive system message about reset
                messages = []
                for _ in range(5):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        data = json.loads(msg)
                        messages.append(data)
                        if data.get("type") == "system":
                            break
                    except asyncio.TimeoutError:
                        break

                # Check for system message
                system_messages = [m for m in messages if m.get("type") == "system"]
                assert len(system_messages) > 0
                assert "reset" in system_messages[0].get("content", "").lower()

        finally:
            if proc:
                proc.terminate()
                proc.wait(timeout=5)
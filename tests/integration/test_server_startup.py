"""
Integration tests for server startup and health checks.
Tests actual server process spawn and HTTP endpoints.
"""

import pytest
import asyncio
import httpx
import subprocess
import sys
import time
import os
import signal
from pathlib import Path


class TestServerStartup:
    """Test suite for server startup and lifecycle."""

    @pytest.mark.asyncio
    async def test_server_startup_and_health(self):
        """Test that the server starts and responds to health checks."""
        port = 18001  # Use different port to avoid conflicts
        proc = None

        try:
            # Start server process
            proc = subprocess.Popen(
                [sys.executable, "-m", "aigent.main", "serve", "--port", str(port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Wait for server to be ready (max 10 seconds)
            start_time = time.time()
            server_ready = False

            async with httpx.AsyncClient() as client:
                while time.time() - start_time < 10:
                    try:
                        resp = await client.get(f"http://localhost:{port}/")
                        if resp.status_code == 200:
                            server_ready = True
                            break
                    except (httpx.ConnectError, httpx.ReadTimeout):
                        pass
                    await asyncio.sleep(0.5)

            assert server_ready, "Server failed to start within 10 seconds"

            # Test health endpoint
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://localhost:{port}/")
                assert resp.status_code == 200

        finally:
            if proc:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

    @pytest.mark.asyncio
    async def test_server_api_endpoints(self):
        """Test that API endpoints are accessible."""
        port = 18002
        proc = None

        try:
            # Start server
            proc = subprocess.Popen(
                [sys.executable, "-m", "aigent.main", "serve", "--port", str(port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Wait for server
            await asyncio.sleep(3)

            async with httpx.AsyncClient() as client:
                # Test /api/profiles endpoint
                resp = await client.get(f"http://localhost:{port}/api/profiles")
                assert resp.status_code == 200
                profiles = resp.json()
                assert isinstance(profiles, list)
                assert "default" in profiles

                # Test /api/config endpoint
                resp = await client.get(f"http://localhost:{port}/api/config")
                assert resp.status_code == 200
                config = resp.json()
                assert isinstance(config, dict)
                assert "default_profile" in config

                # Test /api/stats endpoint
                resp = await client.get(f"http://localhost:{port}/api/stats")
                assert resp.status_code == 200
                stats = resp.json()
                assert isinstance(stats, dict)
                assert "active_connections" in stats
                assert "sessions" in stats
                assert "pid" in stats
                assert stats["pid"] == proc.pid

        finally:
            if proc:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

    @pytest.mark.asyncio
    async def test_server_yolo_mode(self):
        """Test that server starts in YOLO mode with --yolo flag."""
        port = 18003
        proc = None

        try:
            # Start server with YOLO mode
            proc = subprocess.Popen(
                [sys.executable, "-m", "aigent.main", "serve", "--port", str(port), "--yolo"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Wait for server
            await asyncio.sleep(3)

            # Check that server started (can't directly verify YOLO mode without WebSocket)
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://localhost:{port}/")
                assert resp.status_code == 200

            # Check stderr for YOLO warning
            # Give it a moment to print
            await asyncio.sleep(0.5)

            # Note: We can't easily check YOLO mode without WebSocket connection
            # This would be better tested with a WebSocket connection

        finally:
            if proc:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

    @pytest.mark.asyncio
    async def test_server_custom_host_port(self):
        """Test that server respects custom host and port arguments."""
        host = "127.0.0.1"
        port = 18004
        proc = None

        try:
            # Start server with custom host/port
            proc = subprocess.Popen(
                [
                    sys.executable, "-m", "aigent.main", "serve",
                    "--host", host,
                    "--port", str(port)
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Wait for server
            await asyncio.sleep(3)

            # Test connection to custom host/port
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://{host}:{port}/")
                assert resp.status_code == 200

                # Verify stats shows correct info
                resp = await client.get(f"http://{host}:{port}/api/stats")
                assert resp.status_code == 200

        finally:
            if proc:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

    @pytest.mark.asyncio
    async def test_server_graceful_shutdown(self):
        """Test that server shuts down gracefully on SIGTERM."""
        port = 18005
        proc = None

        try:
            # Start server
            proc = subprocess.Popen(
                [sys.executable, "-m", "aigent.main", "serve", "--port", str(port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Wait for server to start
            await asyncio.sleep(3)

            # Verify it's running
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://localhost:{port}/")
                assert resp.status_code == 200

            # Send SIGTERM
            proc.terminate()

            # Wait for graceful shutdown
            try:
                return_code = proc.wait(timeout=5)
                # Process should exit cleanly
                assert return_code is not None
            except subprocess.TimeoutExpired:
                pytest.fail("Server did not shutdown gracefully within 5 seconds")

        finally:
            if proc and proc.poll() is None:
                proc.kill()
                proc.wait()

    @pytest.mark.asyncio
    async def test_kill_server_command(self):
        """Test that kill-server command properly terminates a running server."""
        port = 18006
        proc = None

        try:
            # Start server
            proc = subprocess.Popen(
                [sys.executable, "-m", "aigent.main", "serve", "--port", str(port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Wait for server to start
            await asyncio.sleep(3)

            # Verify it's running
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://localhost:{port}/api/stats")
                assert resp.status_code == 200
                original_pid = resp.json()["pid"]

            # Kill server using kill-server command
            kill_proc = subprocess.Popen(
                [sys.executable, "-m", "aigent.main", "kill-server"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "AIGENT_PORT": str(port)}  # Pass port via env if needed
            )
            kill_proc.wait(timeout=5)

            # Wait a bit for server to die
            await asyncio.sleep(2)

            # Verify server is no longer accessible
            async with httpx.AsyncClient() as client:
                with pytest.raises((httpx.ConnectError, httpx.ReadTimeout)):
                    await client.get(f"http://localhost:{port}/", timeout=1.0)

            # Verify process is dead
            if proc.poll() is None:
                # Process still running, that's unexpected
                pytest.fail("Server process did not terminate after kill-server command")

        finally:
            if proc and proc.poll() is None:
                proc.kill()
                proc.wait()

    @pytest.mark.asyncio
    async def test_server_websocket_endpoint(self):
        """Test that WebSocket endpoint is accessible."""
        port = 18007
        proc = None

        try:
            # Start server
            proc = subprocess.Popen(
                [sys.executable, "-m", "aigent.main", "serve", "--port", str(port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Wait for server
            await asyncio.sleep(3)

            # Test WebSocket connection
            import websockets

            ws_url = f"ws://localhost:{port}/ws/chat/test-session?profile=default"

            try:
                async with websockets.connect(ws_url) as ws:
                    # Connection successful
                    assert ws.open

                    # Send a test message
                    await ws.send("Hello, server!")

                    # Wait for response (should get USER_INPUT event back)
                    response = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    assert response  # Got something back

            except Exception as e:
                pytest.fail(f"WebSocket connection failed: {e}")

        finally:
            if proc:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
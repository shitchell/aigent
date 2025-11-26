# Testing Plan: Unified Client-Server & Shared Sessions

## Overview
This plan covers the verification strategy for the new Client-Server architecture, ensuring robustness in session management, lifecycle handling, synchronization between different client types (CLI and Web), and **preventing regression of CLI rendering issues**.

## 1. Unit Tests (`tests/unit/`)

### `test_persistence.py` (Implemented)
*   **Goal:** Verify `SessionManager` correctly saves/loads JSON and handles file I/O.
*   **Cases:**
    *   Save & Load session (verify data integrity).
    *   List sessions (verify sorting by mtime).
    *   Load non-existent session (graceful None).

### `test_server_lifecycle.py` (Planned)
*   **Goal:** Verify the "Graceful Shutdown" logic.
*   **Cases:**
    *   **Grace Period:** Simulate 0 connections. Verify server does NOT exit immediately.
    *   **Shutdown:** Simulate timer expiry. Verify `sys.exit` or shutdown signal is triggered.
    *   **Reconnection:** Simulate 0 connections -> Timer Start -> New Connection. Verify Timer Cancelled.

### `test_websocket_logic.py` (Planned)
*   **Goal:** Verify the WebSocket protocol implementation in `api.py`.
*   **Cases:**
    *   **Protocol:** Connect, Send "Hello", Receive `TOKEN` events.
    *   **Broadcasting:** Connect Client A and Client B. Send from A. Verify B receives `USER_INPUT` event.

### `test_cli_rendering.py` (CRITICAL - New)
*   **Goal:** Prevent regression of CLI rendering bugs.
*   **Cases:**
    *   **No ANSI Escape Sequences:** Verify output contains no `\x1b[`, `\r`, or malformed sequences like `?[`
    *   **Event Synchronization:** Verify prompt only appears after FINISH event
    *   **Token Buffering:** Verify tokens are buffered and flushed in chunks, not character-by-character
    *   **No Rich Library:** Verify Rich is not imported anywhere in CLI code
    *   **Ready State:** Test `ready_for_input` event properly gates prompt display

## 2. Integration Tests (`tests/integration/`)

### `test_server_startup.py`
*   **Goal:** Verify the actual `aigent serve` process starts and responds.
*   **Cases:**
    *   Spawn process.
    *   HTTP GET `/` (Health check).
    *   Kill process.

### `test_session_switching.py`
*   **Goal:** Verify remote session management via WebSocket commands.
*   **Cases:**
    *   Connect WS.
    *   Send `/fork test-fork`.
    *   Verify subsequent messages go to the new session ID.

## 3. E2E Tests (`tests/e2e/`)

### `test_shared_session_sync.py` (The Gold Standard)
*   **Goal:** Validate real-time synchronization between a CLI subprocess and a Web Browser (Playwright).
*   **Flow:**
    1.  **Launch CLI:** Start `aigent chat --session e2e-test` (which spawns the server).
    2.  **Launch Browser:** Start Playwright, navigate to `http://localhost:8000/?session=e2e-test`.
    3.  **CLI -> Web:**
        *   Send message "Hello form CLI" via CLI stdin.
        *   **Verify:** Playwright sees "Hello from CLI" appear in the DOM.
    4.  **Wait for Response:**
        *   **Verify:** Playwright sees LLM response.
        *   **Verify:** CLI stdout shows LLM response (identical text).
    5.  **Web -> CLI:**
        *   Type "Hello from Web" in browser input and submit.
        *   **Verify:** CLI stdout shows "Hello from Web" (User Input event).
    6.  **Wait for Response:**
        *   **Verify:** Both clients receive the second LLM response.
    7.  **Exit:** Terminate CLI. Verify browser disconnects (or server stays up depending on logic).

### `test_cli_artifacts.py` (CRITICAL - New)
*   **Goal:** Detect rendering artifacts using script recording.
*   **Flow:**
    1.  **Record Session:** Use `script` command or pty to record raw terminal output
    2.  **Send Messages:** Send various message types (short, long, with tools)
    3.  **Analyze Recording:**
        *   Check for carriage returns (`\r`) in unexpected places
        *   Check for ANSI sequences beyond basic colors
        *   Check for cursor movement codes (`\x1b[nA`, `\x1b[nC`)
        *   Verify no "Window too small" messages
    4.  **Stress Test:** Send rapid consecutive messages to test race conditions

## 4. Pre-Flight Checklist
Before merging the `feat/unified-client-server` branch:
1.  All Unit tests pass (especially `test_cli_rendering.py`).
2.  `test_shared_session_sync.py` passes reliably (no race conditions).
3.  `test_cli_artifacts.py` shows ZERO rendering artifacts.
4.  Manual verification of `/fork` and `/session` autocomplete in the CLI.
5.  Verify `--version` flag works correctly.
6.  No regression of fixed bugs (no Rich library, proper event sync).

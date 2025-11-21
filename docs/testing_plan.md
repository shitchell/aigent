# Testing Plan: Unified Client-Server & Shared Sessions

## Overview
This plan covers the verification strategy for the new Client-Server architecture, ensuring robustness in session management, lifecycle handling, and synchronization between different client types (CLI and Web).

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

## 4. Pre-Flight Checklist
Before merging the `feat/unified-client-server` branch:
1.  All Unit tests pass.
2.  `test_shared_session_sync.py` passes reliably (no race conditions).
3.  Manual verification of `/fork` and `/session` autocomplete in the CLI.

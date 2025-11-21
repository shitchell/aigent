# Forking, Sessions, and The Unified Client Architecture

## The Goal
Enable fluid context switching, ephemeral questioning, and collaborative sessions across multiple interfaces (CLI instances, Web UI).

## Terminology

### 1. Persistent Session ("Fork")
A named, persistent conversation history stored on disk.
*   **Command:** `/fork <new_name>`
*   **Behavior:** Clones current history to a new ID, saves it, and *switches* the user to this new session immediately.
*   **Mental Model:** `git checkout -b new-branch`.

### 2. Ephemeral Aside ("Aside")
A transient, one-off question that uses the current context but does not pollute history.
*   **Command:** `/aside <query>`
*   **Behavior:**
    1.  Clones engine state (in memory/temp).
    2.  Executes query.
    3.  Prints result (visually distinct, e.g., bounded by horizontal lines).
    4.  Discards clone.
    5.  Returns to main session.
*   **Mental Model:** A quick "Google search" or checking a manual mid-conversation.

### 3. Session Switching
*   **Command:** `/session <name>`
*   **Behavior:** Switches the active connection to an existing named session.
*   **Autocomplete:** Prioritizes sessions recently accessed *by this specific client instance*, then lists all available sessions.

## Architecture: The "Unified Client" Shift

To support "Shared Sessions" (where Pane A sees what Pane B types) and seamless web integration, `aigent` must evolve from a standalone tool into a Client-Server system.

### Current State (Standalone)
*   `aigent chat` instantiates its own `AgentEngine`.
*   State is local to the process.
*   Synchronization is impossible without complex file watching.

### Target State (Client-Server)
*   **The Daemon:** `aigent serve` runs the `AgentEngine` instances, manages persistence, and exposes a WebSocket API.
*   **The Client:** `aigent chat` becomes a lightweight WebSocket client.
    *   Connects to `ws://localhost:8000`.
    *   Sends user input.
    *   Renders streaming `AgentEvent`s.
*   **Auto-Discovery:** If `aigent chat` cannot find a running server, it can:
    *   A) Start one in the background.
    *   B) Fallback to "Local Mode" (Standalone).

### Implementation Roadmap

#### Phase 1: Core Persistence
Refactor session saving/loading logic out of `api.py` into `src/aigent/core/persistence.py` so it can be shared by the Daemon and Local Mode.

#### Phase 2: Client-Server Protocol
Enhance the WebSocket API to support:
*   **Session Management:** Create, List, Load, Fork.
*   **Event Streaming:** Ensure all events (Tokens, Tools, Approvals) are serialized robustly.
*   **Control Messages:** `/fork` in the CLI sends a `{"type": "fork", "name": "..."}` message to the server, which handles the logic.

#### Phase 3: CLI Refactor
Rewrite `src/aigent/interfaces/cli.py`:
1.  **Connection Mode:** Try connecting to Daemon.
2.  **Rendering:** The `rich.Live` rendering loop becomes the primary view, driven by incoming WebSocket messages.
3.  **Commands:** Slash commands (`/fork`, `/session`) send RPC calls to the server.

#### Phase 4: Local Fallback
Ensure `aigent chat` still works without a server by wrapping `AgentEngine` in a local adapter that mimics the WebSocket interface (or just using the same `CommandRegistry` logic locally).

## UX Details

### `/fork`
*   Syntax: `/fork <name> [optional initial query]`
*   If query provided: Creates fork, switches, and immediately runs the query.
*   If name only: Creates fork, switches, waits for input.

### `/aside`
*   Syntax: `/aside <query>`
*   UI:
    ```
    ────────────── Aside ──────────────
    > What is Nx?
    Nx is a smart build system...
    ───────────────────────────────────
    Resuming session 'main'...
    ```

### `/session`
*   Syntax: `/session <name>`
*   Autocomplete: Smart ordering (LRU per client).
*   Error Handling: If session doesn't exist, warn user (do not create; that's what `/fork` or `/new` is for).


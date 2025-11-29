# User Experience Flow (UX)

**Goal:** Ensure transparency, responsiveness, and seamless collaboration across all interfaces (Web, TUI, REPL).

---
**Alignment:**
*   [Core Value: Session Equality](../../core/VALUES.md#core-beliefs)
*   [Core Principle: Responsiveness](../../core/PRINCIPLES.md#ux-principles)
*   [Core Principle: Unified Client-Server Architecture](../../core/PRINCIPLES.md#unified-client-server-architecture)
---

## 1. Web UI

### 1.1 Welcome Screen
1.  **Start:** When the Web UI is loaded without a `?session=` URL parameter, the user is presented with a welcome screen.
2.  **Options:** This screen allows the user to:
    *   Select a `Profile` to immediately create a new session.
    *   See existing `Profile` options fetched from `/api/profiles`.

### 1.2 Sidebar (Session & User Management)

**Alignment:** [Core Principle: One Contiguous Block](../../core/PRINCIPLES.md#one-contiguous-block)

1.  **Session Listing:** A persistent sidebar displays a list of recently accessed sessions.
    *   **Interaction:** Clicking a session switches the active chat, connecting to the corresponding WebSocket.
2.  **New Chat:** A button (often with a profile dropdown) allows the user to create a new, unique session ID and connect to it.
3.  **Join by ID:** An input field allows users to explicitly enter a session ID and join an existing session.
4.  **Rename Session (Server-Side):** Users can rename the current session.
    *   **Action:** User clicks "Rename", types new name, hits Enter.
    *   **Logic:** Client sends `session:rename` request to Server.
    *   **Broadcast:** Server updates persistence and broadcasts `session:renamed` event.
    *   **Update:** *All* connected clients (Web sidebars, TUI headers) update the displayed name instantly.
5.  **Copy Session ID:** A button to copy the current session's ID to the clipboard, facilitating sharing.
6.  **User Settings (Display Name):** An editable field allows the user to set their display name.
    *   **User ID:** Immutable, generated once, stored in `localStorage`.
    *   **User Name:** Mutable, stored in `localStorage`, sent on connect.
    *   **Display:** Messages show `<username>` (tooltip or config option to show `<username>/<userid>`).

---

## 2. REPL (Read-Eval-Print Loop)

**Context:** The lightweight, compatibility-first interface (`aigent chat --repl`).

### 2.1 REPL Startup

User launches the REPL with `aigent chat --repl`.

#### 1. User runs command
The user executes `aigent chat --repl` (optionally with `--host` and `--port`).

1.  **CLI Dispatcher** detects `--repl` flag.
2.  **REPL Interface** checks for running Daemon on the specified port.
    *   *If Not Found:* Spawns `aigent serve` in background.
3.  **REPL Interface** connects to WebSocket `ws://host:port/ws/chat/{session_id}`.

#### 2. User sees connection status
The terminal displays:
```text
Starting background server...
Connected to Aigent Server.
> 
```

### 2.2 REPL Chat Interaction

#### 1. User types command (Slash Commands)
User types `/`.
1.  **rlcompleter** triggers *only* if at the start of the line.
2.  Shows list of available slash commands (e.g., `/reset`, `/help`).

#### 2. User types message
User types "Hello" and presses Enter.

1.  **REPL Interface** sends `client:input_received` payload.
2.  **Server API** broadcasts event.
3.  **REPL Interface** prints `[User-123] Hello` (from broadcast).

### 2.3 REPL Approval Flow (The "Race")

The Agent requests a tool.

#### 1. Server broadcasts request
Server sends `tool:approval_requested` with `request_id="req_abc123"`.

#### 2. User sees prompt
```text
✋ Permission Request: bash_execute (ID: req_abc123)
   Args: ls -la
   Allow? [y/n/a(lways)/s(mart)] > 
```

#### 3. Scenario A: User approves first
User types `y`.
1.  REPL sends `tool:approval_granted`.
2.  Server executes tool.

#### 4. Scenario B: Peer approves first
While User A is thinking, User B (on Web) clicks "Allow".
1.  Server broadcasts `tool:approval_resolved` (handled by User B).
2.  REPL receives broadcast.
3.  REPL prints: `(Approved by User B)` above the prompt.
4.  If User A still types `y` and Enter:
    *   REPL sends response.
    *   Server ignores duplicate (based on `request_id`) or replies "Already handled".
    *   REPL prints: `Info: Request already resolved.`

---

## 3. TUI (Text User Interface)

**Context:** The rich, widget-based interface (`aigent chat --tui`).

### 3.1 Command Architecture

The TUI merges commands from two sources into the **Command Palette** and **Slash Suggester**:
1.  `TUISharedCommands`: Common commands (Clear Chat, Toggle Lock).
2.  `TUIPaletteCommandsAddons`: Palette-only (Theme Switcher).
3.  `TUISlashCommandAddons`: Input-only (Shortcuts).

### 3.2 TUI Chat Interaction

#### 1. User submits input
User types "Check status".

1.  **TUI App** sends `client:input_received`.
2.  **TUI App** optimistically renders the user message.

#### 2. Agent responds
1.  **Server API** streams `llm:token_received`.
2.  **TUI App** buffers and updates the message bubble in real-time.

### 3.3 TUI Approval Flow

#### 1. Server broadcasts request
Server sends `tool:approval_requested` (`request_id="req_abc123"`).

#### 2. User sees Modal
TUI pushes a **Modal Screen**.

#### 3. Scenario A: User approves
User selects [Allow].
1.  TUI sends `tool:approval_granted`.
2.  Modal closes.

#### 4. Scenario B: Peer approves
User B approves on Web.
1.  Server broadcasts `tool:approval_resolved`.
2.  TUI receives event.
3.  **TUI automatically closes the Modal Screen** (if it matches the `request_id`).
4.  Chat Pane shows system message: "Approved by User B".

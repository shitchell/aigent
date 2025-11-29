# Glossary

*   **Aside**: A transient, one-off query (`/aside`) that uses the current context but branches off to a temporary history, discarding the result after display to avoid polluting the main session.
*   **Black Box Recording**: The mechanism of serializing the full execution state (stack frames, local variables) to a file upon an unhandled exception, enabling rich post-mortem debugging.
*   **Daemon**: The central server process (`aigent serve`) that holds the state, manages the Event Bus, and persists sessions.
*   **Dispatcher**: The core engine component responsible for routing events to registered handlers using dynamic dependency injection.
*   **Event Bus**: The central nervous system where all application logic occurs via event emission and handling.
*   **Fork**: To clone the current session's history into a new, persistent named session (`/fork`), allowing the user to branch the conversation.
*   **Handles Pattern**: The architectural pattern where functions are decorated with `@handles("event")` and declare their dependencies in their signature, allowing the Dispatcher to inject context dynamically.
*   **REPL Mode**: The "Read-Eval-Print Loop" interface (`aigent chat --repl`). A lightweight, compatibility-focused command-line interface.
*   **Shared Session**: A session identified by a unique ID that multiple clients (CLI, Web) can connect to simultaneously. All users in a shared session are peers with equal control.
*   **TUI Mode**: The "Text User Interface" (`aigent chat --tui`). A rich, widget-based terminal interface using Textual.
*   **YOLO Mode**: A mode where safety rails (like approval dialogs for shell execution) are disabled, prioritizing autonomy and speed.

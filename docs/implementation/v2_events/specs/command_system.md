# Specification: Command System

**Module:** `src.aigent.handlers.commands`

## Overview
The Command System intercepts user input starting with `/` (Slash Commands) and dispatches specific events, bypassing the LLM.

## Architecture

### 1. The Interceptor
*   **Handler:** `on_client_input_command_check`
*   **Event:** `CLIENT_INPUT_RECEIVED`
*   **Priority:** 100 (Runs before LLM)
*   **Logic:**
    1.  Checks if content starts with `/`.
    2.  Parses command name (`/reset` -> `reset`).
    3.  Dispatches `command:{name}` (e.g., `command:reset`).
    4.  The LLM Handler (Priority 0) sees the `/` prefix and ignores the message.

### 2. Command Handlers
Plugins or Core modules listen for specific command events.

```python
@handles("command:reset")
async def on_reset(session):
    session.clear()
```

## Core Commands

| Command | Event | Description |
| :--- | :--- | :--- |
| `/reset` | `command:reset` | Clears session history. |
| `/help` | `command:help` | Lists available commands. |

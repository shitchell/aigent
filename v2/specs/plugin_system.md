# Specification: Plugin System

**Module:** `src.aigent.core.plugins`

## Overview
The Plugin System allows users to extend Aigent's functionality by dropping Python scripts into `~/.aigent/plugins/`.

## Mechanism

### 1. Discovery
On startup, `src/aigent/core/plugins.py` scans the configured plugin directory (default: `~/.aigent/plugins`).

### 2. Loading
It imports any `.py` file or directory package found.
*   **Safety:** Errors during import are logged, but do not crash the daemon.

### 3. Registration
Plugins use the standard `@handles` decorator. Simply importing the module registers its handlers with the `bus`.

## Example Plugin

```python
from aigent.core.events import handles, bus, register_signals
from strenum import StrEnum

class MySignals(StrEnum):
    MY_EVENT = "my:event"

register_signals(MySignals)

@handles("client:input_received")
async def on_input(message):
    if "ping" in message.content:
        await bus.dispatch(MySignals.MY_EVENT)
```

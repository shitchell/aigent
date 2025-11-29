# Design Decisions

**Status:** Approved
**Date:** 2025-11-28

---
**Alignment:**
*   [Core Value: Simplicity in Interface, Power in Core](../../core/VALUES.md#simplicity-in-interface-power-in-core)
*   [Core Principle: Dependencies](../../core/PRINCIPLES.md#managed-dependencies)
---

## 1. In-Memory Event Bus

### Decision
The system uses a custom, in-memory `Dispatcher` with Dependency Injection capabilities.

### Rationale
*   **Live Object Passing:** We require the ability to pass live Python objects (such as `WebSocket` connections and `Session` instances) directly to handlers. Distributed message brokers (Redis/RabbitMQ) require serialization, which would sever these references.
*   **Performance:** `asyncio` function calls introduce negligible overhead (nanoseconds) compared to network-based brokers (milliseconds), ensuring the CLI feels "instant."
*   **Deployment Simplicity:** Users can install the tool via `pip` without needing to configure external services like Docker containers for message queues.

## 2. Dependency Injection ("Handles" Pattern)

### Decision
Event handlers declare their dependencies (e.g., `user: User`, `session: Session`) in their function signatures. The Dispatcher inspects these signatures and injects matching objects from the event context.

### Rationale
*   **Decoupling:** Handlers do not need to know the structure of a global "Context" object. They simply request the specific data they need.
*   **Testability:** Functions with explicit dependencies are trivial to unit test. We can mock a `User` object and pass it in, rather than mocking a complex global state container.
*   **Refactoring Safety:** The event payload can evolve (adding new keys) without breaking existing handlers, provided the keys they rely on remain available.

## 3. Black Box Recording

### Decision
Upon an unhandled exception in an event handler, the system serializes the current execution state (stack trace, local variables) to a file.

### Rationale
*   **AI-Native Debugging:** "I want to ensure we have a system which drops pickled exception objects... so that an agent will see it." Providing an LLM with the full variable state at the moment of a crash allows for significantly more accurate diagnosis than a simple textual traceback.
*   **Async Complexity:** Debugging asynchronous race conditions is notoriously difficult; a "snapshot" of the state is often the only way to reconstruct the failure sequence.

## 4. Single-Process Architecture

### Decision
The `aigent serve` process acts as the single source of truth ("The Daemon"). The CLI and Web UI are purely display clients.

### Rationale
*   **Synchronization:** Ensuring that multiple clients (e.g., two users in a shared session) see the exact same state is trivial when that state lives in one process.
*   **Conflict Resolution:** Managing file locks and write conflicts is simplified when all operations funnel through a single Event Bus.

## 5. Configuration & Isolation

### Decision
*   **Root Options:** `aigent --host <host> --port <port>` configuration applies globally to both `chat` and `serve` modes.
*   **Test Isolation:** Automated tests must bind to random or reserved atypical ports to prevent collisions with running user instances.
*   **No Backwards Compatibility:** "We don't care about backwards compatibility." We are free to break file formats (session JSONs) or API signatures to achieve the architectural goals of V2 without being held back by legacy constraints.

## 6. Pydantic Everywhere

### Decision
We prefer Pydantic models for all data structures, especially at the API boundary (WebSockets) and for internal event payloads where strictness is required.

### Rationale
*   **Static Safety:** "Religious level type checking." Pydantic combined with `mypy` ensures that data shapes are validated at compile time and runtime.
*   **Schema Definition:** Pydantic models serve as the definitive schema for the Event Bus, reducing ambiguity about what keys are available in an event.
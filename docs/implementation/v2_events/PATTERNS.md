# Implementation Patterns

**Purpose:** Technical specifications for the V2 codebase.

---
**Alignment:**
*   [Core Principle: The "Handles" Pattern](../../core/PRINCIPLES.md#architecture-the-handles-pattern)
*   [Core Value: Strictness is Safety](../../core/VALUES.md#development-craft)
---

### 1. The "Handles" Pattern

We use a decorator-based registration system with dynamic dependency injection.

**The Decorator:**
```python
@handles(event_name: str, priority: int = 0)
```

**The Handler Signature:**
Handlers define what they need. The Dispatcher matches these arguments against the Event Context using the [Name + Type Matching Algorithm](../../../src/aigent/core/events.py).

*   *Example:*
    ```python
    @handles(CoreSignal.CLIENT_INPUT_RECEIVED)
    async def on_message(session: Session, message: Message, user: User):
        # 'session', 'message', and 'user' objects are injected automatically by TYPE
        # We prefer passing rich Objects over primitives (e.g. Pass User, not user_id)
        await session.append(message)
    ```

**Dependency Injection Rules:**
1.  **Objects > Primitives:** Always prefer passing full objects (`User`, `Session`, `Message`) over IDs or raw strings. This enables type-based matching and reduces ambiguity.
2.  **Strict Primitives:** If you must pass a primitive (`int`, `str`, `bool`), the handler argument name **MUST** match the event context key exactly.
    *   *Good:* Event has `retries=3`. Handler has `def func(retries: int)`.
    *   *Bad:* Event has `retries=3`. Handler has `def func(count: int)`. (Will fail/skip).
3.  **Loud Failures:** The Dispatcher logs detailed warnings in DEBUG mode when a handler is skipped due to missing dependencies, explaining exactly which argument failed to match.

### 2. Strict Type Enforcement

*   **`mypy --strict`:** All code must pass strict type checking.
*   **`StrEnum`:** We use `StrEnum` for all fixed string sets (Event Types, Roles).
*   **Pydantic at the Edge:** We use Pydantic Models to define and validate all data entering or leaving the system (WebSocket messages, API payloads).

**Rationale:**
*   **Robustness:** Strict typing catches errors at build time, not runtime.
*   **Discoverability:** `StrEnum` and Pydantic models provide IDE autocompletion and clear documentation of available values/fields.
*   **Safety:** We do not want magic strings propagating through the system.

### 3. Black Box Debugging

*   **Serialization:** We use `dill` (or robust `pickle`) to serialize stack frames.
*   **Sanitization:** (Future) We will implement filters to scrub secrets (API keys) from crash dumps before writing to disk.

**Rationale:**
*   **AI-Native Debugging:** "I want to ensure we have a system which drops pickled exception objects... so that an agent will see it." Providing an LLM with the full variable state allows for rapid resolution of complex async bugs.

### 4. Logging Standards

*   **Format:** `%(asctime)s [%(levelname)s] %(name)s: %(message)s`
*   **Levels:**
    *   `DEBUG`: Payload details, event dispatching arguments, **handler skip reasons**.
    *   `INFO`: High-level flow (Session connected, Tool executed).
    *   `WARNING`: Recoverable errors (Client disconnect, API timeout).
    *   `ERROR`: Unhandled exceptions, logic failures.

**Rationale:**
*   **Observability:** "Loud Dispatching" ensures that if a handler isn't running, we know exactly why (mismatch vs error) without guessing.

### 5. File Structure Convention

*   `src/aigent/core/`: The invariant engine (Events, Debugging, Logging).
*   `src/aigent/server/`: The Daemon and WebSocket API.
*   `src/aigent/interfaces/`: The view layers (CLI, TUI).
*   `src/aigent/handlers/`: The business logic (where `@handles` functions live).

**Rationale:**
*   **Separation of Concerns:** Keeps the engine (Core) distinct from the logic (Handlers) and the presentation (Interfaces).
*   **Discoverability:** A new developer knows exactly where to put a new feature (Handlers) vs a new UI widget (Interfaces).
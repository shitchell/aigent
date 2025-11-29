# Specification: Event Bus

**Module:** `src.aigent.core.events`

## Overview
The Event Bus is the central nervous system of Aigent. It routes signals to handlers using a **Dependency Injection** pattern similar to FastAPI.

## Core Components

### 1. `CoreSignal` (StrEnum)
Defines the lifecycle events guaranteed to exist.
*   `CLIENT_CONNECT` / `CLIENT_DISCONNECT`
*   `CLIENT_INPUT_RECEIVED`
*   `SYSTEM_OUTPUT`
*   `SYSTEM_ERROR`

### 2. `Dispatcher` (Singleton: `bus`)
*   **Registration:** Stores handlers in a `dict[event_name, list[Handler]]`.
*   **Dispatching:** `async def dispatch(event_name, **context)`
*   **Injection:**
    *   Iterates over registered handlers.
    *   Inspects `handler.func` signature.
    *   Injects values from `context` based on **Name** (for primitives) or **Type** (for objects).
    *   **Loud Failure:** If a required argument is missing, it logs a `DEBUG` warning and skips the handler.

### 3. `@handles` Decorator
*   **Usage:** `@handles(Signal.NAME, priority=10)`
*   **Effect:** Registers the decorated function with the global `bus`.

## Dependency Injection Rules

1.  **Primitives:** `int`, `str`, `bool`. Must match by **Name**.
    *   Context: `{"retries": 3}` matches `def func(retries: int)`.
2.  **Objects:** `User`, `Session`. Match by **Type** (preferred) or Name.
    *   Context: `{"user": UserObj}` matches `def func(u: User)`.
3.  **Missing:** If a non-optional argument cannot be resolved, the handler is **Skipped**.

## Error Handling
*   Handlers are wrapped in `try/catch`.
*   Exceptions trigger a recursive `dispatch(CoreSignal.SYSTEM_ERROR, ...)`.
*   The system does *not* crash on handler failure.

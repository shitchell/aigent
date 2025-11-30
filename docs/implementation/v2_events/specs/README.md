# Specifications

This directory contains technical specifications for individual subsystems. Each spec defines the contract and behavior for a specific component.

## Purpose

Specification documents provide:

- **API contracts** — Function signatures, parameters, return types
- **Data structures** — Schemas, enums, type definitions
- **Behavior** — How the component responds to inputs
- **Error handling** — Failure modes and recovery

## Files

| File | Description |
|------|-------------|
| [`event_bus.md`](event_bus.md) | Event bus signals, dispatcher, and handler registration |
| [`command_system.md`](command_system.md) | Slash command parsing and execution |
| [`debug_system.md`](debug_system.md) | Crash capture, serialization, and analysis |
| [`plugin_system.md`](plugin_system.md) | Plugin discovery, loading, and registration |

## Spec Document Structure

Each specification should include:

1. **Overview** — What the subsystem does (1-2 sentences)
2. **API** — Public interface (functions, classes, events)
3. **Behavior** — How it responds to inputs
4. **Error handling** — Failure modes and recovery
5. **Examples** — Usage examples where helpful

## When to Reference

- **Implementing a subsystem** — Follow the spec exactly
- **Integrating with a subsystem** — Understand the API contract
- **Debugging** — Verify behavior matches the spec
- **Code review** — Ensure changes comply with the spec

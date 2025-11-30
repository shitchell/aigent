# Core Documentation

This directory contains the philosophical foundation of the project—documents that define identity, values, and principles. These are the "north star" documents that guide all other decisions.

## Purpose

Core documentation answers fundamental questions:

- **Who** does this project serve?
- **Why** does it exist?
- **What** principles guide development?

These documents should change infrequently. If you find yourself wanting to modify them often, the content may belong in [`implementation/`](../implementation/) instead.

## Files

| File | Description |
|------|-------------|
| [`IDENTITY.md`](IDENTITY.md) | Defines the project's purpose, target audience, and non-negotiable goals |
| [`PRINCIPLES.md`](PRINCIPLES.md) | Engineering laws that persist across refactors and versions |
| [`VALUES.md`](VALUES.md) | Cultural and ethical foundations; decision-making heuristics |

## Reading Order

For newcomers to the project:

1. **IDENTITY.md** — Understand what we're building and for whom
2. **VALUES.md** — Understand why we make certain tradeoffs
3. **PRINCIPLES.md** — Understand how we approach implementation

## When to Reference

- **Making architectural decisions** → Check PRINCIPLES.md
- **Prioritizing features** → Check IDENTITY.md (target audience)
- **Resolving tradeoff debates** → Check VALUES.md (decision heuristics)

# Design

This directory contains design rationale and user experience documentation explaining *why* things work the way they do.

## Purpose

Design documentation captures:

- **Decisions** — Architectural choices with tradeoff analysis
- **UX flows** — User interaction patterns for different interfaces
- **Rationale** — The reasoning behind non-obvious choices

## Files

| File | Description |
|------|-------------|
| [`decisions.md`](decisions.md) | Approved architectural decisions with rationale and tradeoffs |
| [`ux_flow.md`](ux_flow.md) | User experience flows for different interfaces and modes |

## Decisions vs. Specs

- **Design decisions** answer "why did we choose X over Y?"
- **Specs** answer "how does X work in detail?"

A decision might be "use an in-memory event bus instead of a distributed broker"—the corresponding spec would define the event bus API and behavior.

## When to Reference

- **Questioning an approach** — Check if it was a deliberate decision
- **Proposing alternatives** — Understand what tradeoffs were already considered
- **Adding new interfaces** — Follow established UX patterns
- **Onboarding** — Understand the reasoning behind the system

# Version Documentation

This directory contains technical documentation for this implementation version.

## Directory Structure

```
.
├── PATTERNS.md            # Implementation patterns and conventions
├── architecture/          # System-level design and component interaction
├── design/                # Design decisions and user experience flows
└── specs/                 # Technical specifications for subsystems
```

## Subdirectories

### [`architecture/`](architecture/)

High-level system design documentation:

- Component diagrams
- Data flow descriptions
- Integration points
- System boundaries

### [`design/`](design/)

Design rationale and user experience:

- Architectural decisions with tradeoff analysis
- UX flows for different interfaces/modes
- Interaction patterns

### [`specs/`](specs/)

Technical specifications for individual subsystems:

- API contracts
- Data structures
- Protocol definitions
- Subsystem behavior

## Files

| File | Description |
|------|-------------|
| [`PATTERNS.md`](PATTERNS.md) | Implementation patterns, conventions, and idioms used in this version |

## Reading Order

1. **PATTERNS.md** — Understand the conventions before diving into specifics
2. **architecture/** — Get the big picture of how components interact
3. **design/** — Understand why certain approaches were chosen
4. **specs/** — Reference as needed for implementation details

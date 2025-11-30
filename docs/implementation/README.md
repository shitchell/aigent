# Implementation Documentation

This directory contains version-specific technical documentation. Each subdirectory represents a major version, prototype, or architectural iteration of the project.

## Purpose

Implementation documentation captures:

- **Architecture** — How components are structured and interact
- **Design decisions** — What tradeoffs were made and why
- **Specifications** — Technical details of subsystems
- **Patterns** — Reusable approaches specific to this version

## Directory Structure

Each version directory should follow a consistent structure:

```
v1_prototype/
├── README.md              # Overview of this version
├── PATTERNS.md            # Implementation patterns used
├── architecture/          # System-level design docs
├── design/                # Design decisions and UX flows
└── specs/                 # Technical specifications

v2_web-ui/
├── README.md
├── PATTERNS.md
├── architecture/
├── design/
└── specs/
```

## Naming Convention

Version directories use the format: `v{N}_{descriptor}`

- `v1_prototype` — Initial prototype
- `v2_web-ui` — Web UI-focused rewrite
- `v3_distributed` — Distributed architecture iteration

The descriptor should be a brief, memorable identifier for the version's primary focus or distinguishing characteristic.

## Versioning Philosophy

- **Don't delete old versions** — Historical context is valuable
- **Reference, don't duplicate** — Link to previous versions for unchanged concepts
- **Document divergence** — Explain what changed and why between versions

## Current Version

See subdirectories for available versions. The most recent version represents the current implementation target.

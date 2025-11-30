# 💡 Project Principles

**Purpose:** This document defines the "How." These are the immutable engineering laws of Aigent, designed to persist across any major refactor or even language change.

---

### 🏗️ Event-Driven Architecture
We follow a strict **Event-Driven Architecture** with a strong emphasis on **Dependency Injection**.

* **Decoupled Components:** All logic flow is orchestrated through explicit events, promoting loose coupling between system components.
* **Declarative Needs:** Components (handlers, services) declare their input requirements, and the system dynamically provides the necessary context.

### 🧩 "One Contiguous Block"
To add a feature or implement a change, the goal is to require modifications within **one contiguous block of code** whenever possible.

* This principle promotes high cohesion and reduces the cognitive load of navigating dispersed logic.

### 🔌 Unified Client-Server Architecture
* **Centralized Logic:** The core application logic resides in a centralized server process.
* **Thin Clients:** User interfaces (CLI, Web) act as thin clients, primarily responsible for input and rendering, reflecting the server's state.
* **Consistent Experience:** All connected clients should experience a synchronized and consistent view of the application state.

### 🛡️ Robustness & Integrity
* **Strict Type Checking:** We enforce strict typing universally. This guards against runtime errors and serves as compile-time documentation.
* **Universal Linting:** All code, scripts, and configurations must be linted. This enforces consistency and catches potential issues early.
* **Comprehensive Crash Analysis:** When failures occur, the system provides rich, actionable context (snapshots of state, entire pickled exceptions/frames where possible) for post-mortem analysis.
* **Resilient Execution:** The system is designed to gracefully handle component failures, ensuring that a single error does not bring down the entire application.
* **Comprehensive Automated Testing:** We test everything. This includes unit tests for isolated logic, mock tests for integrations, and E2E tests using browser/UI testing frameworks and live scenarios.
  * When features are implemented, write tests cases for them
  * When bugs are found:
    1. Write a failing test case that should capture the bug
    2. Implement and commit a fix (do not commit the test yet)
    3. Re-run the test case
    * IF the re-run does not result in a success:
      * Revert the committed fix
      * Start back at #1 and re-try writing the failed test
      * SUCCESS: we can `run the test -> it fails -> implement the fix -> re-run the test -> it succeeds`
      * This ensures we maintain robust, reliable tests that accurately capture bugs and ensure we catch them if they ever appear again

### ✒️ Code Craft & Readability
* **Concise Functions:** Keep functions small and focused (ideally under 50 lines). If logic grows complex, split it into smaller, named sub-functions to foster readability and testability.
* **Explicit and Descriptive Naming:** Names for variables, functions, and files must be clear and self-explanatory, even if long. Ambiguity is the enemy of maintainability.
* **Internal Reusability:** Where logic can be hypothetically/feasibly shared in some future scenario: genericize it and extract it into dedicated shared libraries or modules. We prioritize building reusable internal tools over duplicating logic.
* **Unique and consistent terminology:** Where we re-use existing concepts, re-use the existing terminology. BUT, if we introduce a tweak or modification to an existing concept, we should create unique terminology that has no overlap with ambiguous, pre-existing nomenclature.

### 📦 Managed Dependencies
* **Prioritize Stability:** Core logic should favor stable, performant, and well-understood components, ideally from standard libraries.
* **Isolated Integration:** When external frameworks are used, they are integrated with clear boundaries, preventing their internal abstractions from dictating the core system's architecture.

### 🎨 UX Principles
* **Responsiveness:** User interactions should feel immediate and fluid.
* **Clarity over Obscurity:** The system avoids implicit behaviors; actions and states are made explicit to the user.

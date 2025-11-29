# 🧘 Project Values

**Purpose:** This document describes the "Why"—the cultural and ethical choices behind the code.

---

### ⚖️ Core Beliefs
*   **User Control:** AI should be a tool, not a black box. The user is always the pilot; the AI is the copilot.
*   **Privacy First:** Context stays local. We only send what is necessary to the LLM API.
*   **Simplicity in Interface, Power in Core:** The CLI should be clean and responsive, hiding the immense complexity of the event bus and state management.
*   **Session Equality:** In a shared session, all users are peers. Anyone can approve a tool, rename the session, or type input. There are no "admins" within a shared session unless the session was explicitly locked at creation.

---

### 🛠️ Development Craft
*   **Strictness is Safety:** We rely on **Strict Typing** and ** rigorous testing**. In an async, event-driven system, runtime errors are nightmares. We prevent them at compile/check time.
*   **Hackability:** The system is designed to be extended. We value **"Drop-in" Extensibility**. A user should be able to write a python script (async or sync), drop it in a folder, and have the agent instantly gain new powers.
*   **One Contiguous Block:** We strive to keep related logic together. Adding a feature should not require "shotgun surgery" across 5 different files.

---

### 🏆 Defining Success
*   **Trust:** Success is when a user lets the agent run `bash_execute` without reading the command closely, because they trust the system's safety rails.
*   **Flow:** Success is when the agent feels like a natural extension of the developer's thought process, not a clunky tool they have to "manage."
*   **Resilience:** Success is when a plugin crashes, and the system logs the error, notifies the user, and *keeps running*.

---

### 🧠 Decision Heuristics (Tie-Breakers)

When faced with two valid technical choices, use these heuristics to decide.

#### 1. Build vs. Buy
*   **The "LLM Week" Rule:** If a feature requires a library that is so complex it would take an LLM "weeks" (which usually means hours of focused generation/debugging) to reproduce, **Buy It** (use the library).
*   **The "LLM Hour" Rule:** If the logic can be generated and stabilized by an LLM in under an hour, **Build It**. We prefer owning the code over importing bloat.

#### 2. Architecture vs. Speed
*   **No Shortcuts:** If the "Right Way" involves refactoring the Core Event Bus and the "Fast Way" is a hack, **block the feature and refactor**. We prioritize long-term stability over short-term feature delivery.
*   **LLM Time is Cheap:** Do not optimize for "developer hours" based on human speed. An LLM can refactor a core module in minutes. Do not let the "effort" of a refactor deter you from the correct architectural choice.

#### 3. Core Stability vs. Edge Agility
*   **Core Perfection:** Code in `src/aigent/core` must have 100% unit test coverage and handle every edge case.
*   **The Bugfix Loop:** If a test fails:
    1.  Reproduce with a failing test case.
    2.  Fix the code.
    3.  Verify the test passes.
    4.  **Revert the fix and verify the test fails again.** (Proof of causality).
    5.  Re-apply the fix.

#### 4. Sovereignty vs. Safety
*   **Override Wins:** If a user wants to run `rm -rf /` and explicitly confirms it (or uses a `--yolo` flag), let them. We provide rails, but the user has the keys to the gate.
*   **Debug Privacy:** We default to dumping rich crash data (stack frames, locals) for debugging, but we warn users if they are in `DEBUG` mode that this may contain sensitive info.

#### 5. Interface Philosophy
*   **REPL:** Prioritizes **Compatibility**. Must run on old terminals, SSH sessions, and minimal environments.
*   **TUI / Web:** Prioritizes **Aesthetics & Features**. Go wild with animations, complex widgets, and modern interactions.

#### 6. The "Partner" Persona
*   **Proactive Facilitator:** The agent is not just a chatbot. It is a partner that facilitates work. It should offer to run commands, suggest fixes, and manage the environment actively.
*   **Remote Enabler:** A key use case is enabling a user to work effectively on a remote server (e.g., via mobile voice-to-text) by acting as the intelligent hands-on-keyboard.
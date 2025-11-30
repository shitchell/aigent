# 🧭 Project Identity

**Purpose:** This document defines the "North Star" of the Aigent project—its fundamental purpose, audience, and boundaries.

---

### 🎯 Overarching Goal

Aigent aims to be the **definitive local-first AI Pair Programmer** featuring shared, collaborative real-time sessions between clients.
It transforms the Large Language Model from a passive chatbot into a **proactive, integrated system agent** that lives in your terminal and browser, capable of complex reasoning, file manipulation, and system interaction in sessions that can be collaboratively shared between users.

---

### 👥 Target Audience
* **Software Engineers:** Developers who want an AI partner that can run tests, edit code, and debug without leaving the terminal.
* **Power Users:** Users comfortable with CLI environments who value efficiency and scriptability.
* **Privacy Advocates:** Individuals who want powerful AI assistance without sending their entire codebase context to a third-party SaaS (beyond the LLM API call itself).
* **Teams:** Planning and working on an LLM-assisted projected.
* **Remote Devs:** Who want a simple web interface to work with an LLM on a remote server with full fileystem and shell access.

---

### 🚫 Non-Audience
* **Non-Technical Users:** This is a CLI-first tool. It is not a "magic app builder" for people who don't know what a terminal is.
* **Enterprise Compliance Managers:** While secure, this tool is designed for individual/team agility, not rigid corporate audit logging (yet).

---

### 📌 Non-Negotiable Goals
1.  **Local Sovereignty:** The agent runs *locally*. It does not depend on a proprietary backend server (other than the LLM provider).
2.  **Explicit Consent:** The user must be able to dictate how and when the agent is able to execute any tool.
3.  **Transparency:** The user must always know what the agent is doing. No hidden background processes or phantom edits.

---

### 🗺️ Project Boundaries
* **Not a Cloud Service:** Aigent is software you run, not a service you subscribe to.
* **Not an IDE Replacement:** It integrates with your workflow; it doesn't replace your editor (though it might control it).

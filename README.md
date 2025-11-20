# Aigent

A robust, async-first LangChain agent with CLI and Web interfaces.

## 🚀 Features

*   **Dual Interface**:
    *   **CLI**: Flicker-free, async REPL via `prompt_toolkit`.
    *   **Web Daemon**: Collaborative, multi-session UI via FastAPI + WebSockets.
*   **Collaboration**: Share a session URL (`?session=chat-xyz`) with a friend to debug code together in real-time.
*   **Persistence**: All chats are auto-saved to `~/.aigent/sessions/`. You never lose context.
*   **Multi-Profile**: Switch between "Coder" (Claude), "Cheap" (Gemini), or "Grok" instantly via the UI or CLI.
*   **Core Tools**:
    *   `fs_read` / `fs_write`: Manage files.
    *   `fs_patch`: Surgical find-and-replace with Diff output.
    *   `bash_execute`: Run shell commands (Use with caution!).
*   **Plugin System**: Drop Python scripts into `~/.aigent/tools/` to instantly extend capabilities.
*   **Memory**: Auto-loads context from `/etc/aigent`, `~/.aigent`, and local project files.

## 📦 Installation

1.  Clone and install in editable mode (recommended for development):
    ```bash
    git clone https://github.com/shitchell/aigent.git
    cd aigent
    pip install -e ".[dev]"
    ```

## 🔑 Setup & Configuration

### 1. API Keys
Aigent looks for environment variables. You can set them in your shell or create a `.env` file in the directory where you run the command.

**Create a `.env` file:**
```bash
OPENAI_API_KEY="sk-..."
ANTHROPIC_API_KEY="sk-ant-..."
GOOGLE_API_KEY="AIza..."  # For Gemini
XAI_API_KEY="xai-..."     # For Grok
```

### 2. Profiles & Security
Configure your agents in `~/.config/aigent/settings.yaml`.

```yaml
settings:
  default_profile: "default"
  tool_call_preview_length: 120
  # Security: Restrict file operations to these directories
  allowed_work_dirs: [".", "~/projects"]

server:
  host: "127.0.0.1"
  port: 8000
  static_dir: "static" # Path to web UI assets

# Define Authorization Policies
permission_schemas:
  - name: "default"
    default_policy: "ask" # Ask user before running unknown tools
    tools:
      fs_read: "allow"    # Safe to read files
      fs_write: "ask"     # Ask before writing
      bash_execute: "ask" # ALWAYS ask before running shell commands

profiles:
  default:
    name: "default"
    model_provider: "openai"
    model_name: "gpt-4o-mini"
    permission_schema: "default" # Link to permission schema
```

### 3. Persistent Memory / Context
Aigent reads markdown files on startup to build its system prompt.
*   **System:** `/etc/aigent/AIGENT.md` (Admins)
*   **Global:** `~/.aigent/AIGENT.md` (Good for "Always remember I am a Python dev")
*   **Project:** `./.aigent/AIGENT.md` (Good for "This project uses FastAPI")

## 🛠 Usage

### CLI Chat
```bash
aigent chat
# or
aigent chat --profile coder
```
**YOLO Mode (Danger!):**
Disable all permission prompts for this session:
```bash
aigent chat --yolo
```

### Web Daemon
```bash
aigent serve
# or override defaults
aigent serve --port 9000
```
**Features:**
*   **Collaboration:** Share the URL (`?session=chat-abc`) to debug together.
*   **Human-in-the-Loop:** If the Agent tries to run `bash_execute`, a permission card appears. You can Allow, Deny, or "Always Allow" for the session.
*   **Live Status:** See "Typing..." indicators and tool outputs in real-time.

## 🔌 Plugins (Tools)

Create a folder in `~/.aigent/tools/my_tool/` and add a `main.py`:

```python
# ~/.aigent/tools/weather/main.py
from langchain_core.tools import tool

@tool
def get_weather(city: str) -> str:
    """Get the weather for a city."""
    return "Sunny, 25C"
```
It will be automatically loaded next time you run `aigent`.

## 🧪 Testing

We use `pytest`.

**Run Unit Tests (Fast, Mocked):**
```bash
pytest tests/unit
```

**Run Live Integration Tests (Real API Calls - Costs Money):**
```bash
pytest tests/integration --live
```
*(Note: You must provide the `--live` flag to run real API tests)*
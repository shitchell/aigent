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
    git clone https://github.com/shitchell/langchain-simple.git
    cd langchain-simple
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

### 2. Profiles
Configure your agents in `~/.config/aigent/settings.yaml`.

```yaml
settings:
  default_profile: "default"
  tool_call_preview_length: 120

profiles:
  default:
    name: "default"
    model_provider: "openai"  # or "anthropic", "google", "grok"
    model_name: "gpt-4o-mini"
    temperature: 0.7
    allowed_tools: ["*"]      # Allow all tools

  coder:
    name: "coder"
    model_provider: "anthropic"
    model_name: "claude-3-5-sonnet-20241022"
    temperature: 0.2
    
  cheap:
    name: "cheap"
    model_provider: "google"
    model_name: "gemini-1.5-flash"
    temperature: 0.5
```

### 3. Persistent Memory / Context
Aigent reads markdown files on startup to build its system prompt.
*   **Global:** `~/.aigent/MYAGENT.md` (Good for "Always remember I am a Python dev")
*   **Project:** `./.aigent/MYAGENT.md` (Good for "This project uses FastAPI")

## 🛠 Usage

### CLI Chat
```bash
aigent chat
# or
aigent chat --profile coder
```

### Web Daemon
```bash
aigent serve --port 8000
# Then open http://localhost:8000
```
**Collaboration:** Copy the URL from your browser (e.g., `http://localhost:8000/?session=chat-abc`) and send it to a friend. If they open it, they will join the same session and see the history.

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
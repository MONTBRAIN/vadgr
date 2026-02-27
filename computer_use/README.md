# Computer Use Engine

Gives LLM agents eyes (screenshots) and hands (mouse, keyboard) to execute tasks autonomously on any desktop.

## Setup

```bash
python3 -m venv computer_use/.venv
source computer_use/.venv/bin/activate
pip install -r computer_use/requirements.txt
```

## Two Modes

### Library Mode (agent calls engine)

Any LLM agent can use the engine as a tool. The agent decides what to do; the engine provides screenshots and executes actions.

```python
from computer_use import ComputerUseEngine

engine = ComputerUseEngine()
screen = engine.screenshot()          # ScreenState with PNG bytes
engine.click(500, 300)                # left click
engine.type_text("hello world")       # type into focused field
engine.key_press("ctrl", "s")         # keyboard shortcut
engine.scroll(500, 400, -3)           # scroll down
element = engine.find_element("Save") # find UI element by description
engine.click_element(element)         # click found element
```

### Autonomous Mode (engine calls LLM)

The engine runs its own loop: screenshot, ask LLM what to do, execute action, verify, repeat.

```python
from computer_use import ComputerUseEngine

engine = ComputerUseEngine(provider="anthropic")
results = engine.run_task("Open Notepad and type hello")
```

Or from the command line:

```bash
PYTHONPATH=. python -m computer_use "Open Notepad" --provider anthropic
PYTHONPATH=. python -m computer_use --screenshot output.png
PYTHONPATH=. python -m computer_use --info
```

## Platforms

| Platform | Screenshots | Actions | Accessibility |
|----------|-------------|---------|---------------|
| WSL2 | PowerShell bridge | PowerShell bridge | UI Automation via PS |
| Linux/X11 | mss | xdotool | AT-SPI2 (stub) |
| Windows | Win32 GDI | SendInput | UI Automation (stub) |
| macOS | screencapture | osascript/cliclick | AX API (stub) |

## LLM Providers

Configure in `config.yaml` or via environment variables:

| Provider | Env Variable | Config Key |
|----------|-------------|------------|
| Anthropic | `ANTHROPIC_API_KEY` | `providers.anthropic.api_key` |
| OpenAI | `OPENAI_API_KEY` | `providers.openai.api_key` |

## MCP Server

The engine can run as an MCP server, exposing all 14 tools (screenshot, click, type, etc.) to any MCP-compatible client. The engine stays running persistently, so each action takes ~100ms instead of ~1.4s.

### Start the server

```bash
# stdio transport (default, used by Claude Code / Cursor)
PYTHONPATH=. python -m computer_use.mcp_server

# SSE transport (for web clients or remote connections)
PYTHONPATH=. python -m computer_use.mcp_server --transport sse --port 8000
```

### Connect from Claude Code

Add to `.mcp.json` in the project root:

```json
{
    "mcpServers": {
        "computer_use": {
            "type": "stdio",
            "command": "python",
            "args": ["-m", "computer_use.mcp_server"],
            "cwd": "/path/to/Agent-Forge",
            "env": { "PYTHONPATH": "." }
        }
    }
}
```

Or use the CLI: `claude mcp add --transport stdio --scope project computer_use -- python -m computer_use.mcp_server`

Tools become available as `mcp__computer_use__screenshot()`, `mcp__computer_use__click()`, etc.

### Connect from Cursor

Add to `.cursor/mcp.json`:

```json
{
    "mcpServers": {
        "computer_use": {
            "command": "python",
            "args": ["-m", "computer_use.mcp_server"],
            "cwd": "/path/to/Agent-Forge",
            "env": { "PYTHONPATH": "." }
        }
    }
}
```

### Available tools

| Tool | Description |
|------|-------------|
| `screenshot()` | Full screen capture (base64 PNG) |
| `screenshot_region(x, y, w, h)` | Region capture |
| `click(x, y)` | Left click |
| `double_click(x, y)` | Double click |
| `right_click(x, y)` | Right click |
| `move_mouse(x, y)` | Move cursor |
| `scroll(x, y, amount)` | Scroll (positive=up) |
| `drag(sx, sy, ex, ey, duration)` | Click-drag |
| `type_text(text)` | Type a string |
| `key_press(keys)` | Key combo ("ctrl+c") |
| `get_screen_size()` | Screen resolution |
| `get_platform()` | Detected OS |
| `get_platform_info()` | Full platform details |
| `find_element(description)` | Find UI element by name |

## Architecture

```
computer_use/
├── core/           # Engine facade, types, ABCs, autonomous loop
├── platform/       # OS-specific backends (WSL2, Linux, Windows, macOS)
├── grounding/      # UI element location (accessibility + vision fallback)
├── providers/      # LLM adapters (Anthropic, OpenAI)
└── tests/          # Unit tests (47 tests)
```

## Tests

```bash
source computer_use/.venv/bin/activate
PYTHONPATH=. python -m pytest computer_use/tests/ -v
```

## Design Principles

1. **Agent-agnostic**: Any vision-capable LLM can use the engine
2. **Vision-only by default**: No browser automation, no DOM inspection
3. **100% our code**: No external computer use frameworks
4. **Cross-platform**: Abstract OS layer, platform-specific backends
5. **Generate mode is sacred**: Existing workflow generation works without this module

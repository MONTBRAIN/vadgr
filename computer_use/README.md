# Computer Use - Desktop Automation Engine

Captures screenshots, locates UI elements, and executes mouse/keyboard actions for autonomous desktop interaction.

This module is **standalone** and works independently without `forge/`.

## What It Does

Provides programmatic control of the desktop through:

- **Screenshots** - full screen or region capture
- **Element grounding** - find UI elements via accessibility APIs + LLM vision
- **Actions** - click, type, scroll, drag, key press
- **Autonomous loop** - screenshot, decide, act, verify cycle
- **Muscle memory** - learns element positions for faster repeated interactions

## Usage

### As a library

```python
from computer_use import ComputerUseEngine

engine = ComputerUseEngine()
screen = engine.screenshot()
engine.click(500, 300)
engine.type_text("hello")
```

### Autonomous mode

```python
engine = ComputerUseEngine(provider="anthropic")
results = engine.run_task("Open Notepad and type hello", max_steps=50)
```

### As an MCP server

Exposes 20+ tools via Model Context Protocol for any MCP-compatible agent:

```bash
python -m computer_use.mcp_server
```

See `.mcp.json.example` in the repo root for configuration.

### CLI

```bash
python -m computer_use "Open the browser and search for Vadgr"
python -m computer_use --screenshot    # Save a screenshot
python -m computer_use --info          # Show platform info
```

## Setup

### Linux

```bash
bash setup-linux.sh
```

### Manual setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set your LLM provider API key:

```bash
export ANTHROPIC_API_KEY="sk-..."
# or
export OPENAI_API_KEY="sk-..."
```

## Architecture

```
computer_use/
├── core/               # Engine facade, types, actions, loop, spatial cache
├── platform/           # OS backends (Linux, Windows, macOS, WSL2)
├── grounding/          # UI element location (accessibility + vision)
├── providers/          # LLM adapters (Anthropic, OpenAI)
├── bridge/             # WSL2 <-> Windows TCP bridge
├── tests/              # Unit tests (pytest)
├── mcp_server.py       # MCP server entry point
├── config.yaml         # Default configuration
└── requirements.txt    # Python dependencies
```

## Platform Support

| Platform | Screenshots | Actions | Accessibility |
|----------|-------------|---------|---------------|
| Linux/X11 | mss | xdotool | AT-SPI2 |
| Linux/Wayland (GNOME) | gnome-screenshot | Mutter RemoteDesktop | AT-SPI2 |
| Linux/Wayland (wlroots) | grim | evdev | AT-SPI2 |
| WSL2 | PowerShell bridge | PowerShell bridge | UI Automation |
| Windows | Win32 GDI | SendInput | UI Automation |
| macOS | screencapture | osascript/cliclick | AX API |

## Configuration

Edit `config.yaml` or use environment variables:

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `AGENT_FORGE_DEBUG` | Enable debug screenshots |
| `AGENT_FORGE_DATA` | Custom data directory for cache |
| `CU_MAX_WIDTH` | Max screenshot width for vision |

## Tests

```bash
PYTHONPATH=. .venv/bin/python -m pytest computer_use/tests/ -v
```

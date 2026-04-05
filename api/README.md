# Vadgr API

REST + WebSocket backend for agent management, forge generation, and execution. Agent-agnostic and cross-platform: works on Windows, macOS, and Linux with any CLI agent tool.

## Requirements

- **Python >= 3.12**
- **At least one CLI agent tool** installed and on your PATH

### Install Python

```bash
# Ubuntu/Debian
sudo apt-get install python3.12 python3.12-venv

# macOS (Homebrew)
brew install python@3.12

# Windows
# Download from https://www.python.org/downloads/
```

### Install a CLI agent provider

The API is agent-agnostic. It calls whichever CLI tool is configured in `providers.yaml` as a subprocess. Install at least one:

```bash
# Claude Code
npm install -g @anthropic-ai/claude-code && claude auth

# Codex
npm install -g @openai/codex

# Aider
pip install aider-chat

# Or add your own to providers.yaml -- zero code changes needed
```

The chosen tool must be on your PATH and authenticated.

## Setup

```bash
cd api

# Create virtual environment
python3.12 -m venv .venv

# Activate
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows (cmd)
# .venv\Scripts\Activate.ps1     # Windows (PowerShell)

# Install dependencies
pip install -r requirements.txt
```

## Run

From the **project root** (not `api/`):

```bash
# Linux/macOS
PYTHONPATH=. python -m uvicorn api.main:app --host 127.0.0.1 --port 8000

# Windows (cmd)
set PYTHONPATH=. && python -m uvicorn api.main:app --host 127.0.0.1 --port 8000

# Windows (PowerShell)
$env:PYTHONPATH="."; python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

The API starts at http://127.0.0.1:8000. API docs at http://127.0.0.1:8000/docs.

### Environment variables

All prefixed with `AGENT_FORGE_`:

| Variable | Default | Description |
|---|---|---|
| `AGENT_FORGE_HOST` | `127.0.0.1` | Bind address |
| `AGENT_FORGE_PORT` | `8000` | Bind port |
| `AGENT_FORGE_DATABASE_PATH` | `data/agent_forge.db` | SQLite database path |
| `AGENT_FORGE_CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed CORS origins |
| `AGENT_FORGE_DEFAULT_PROVIDER` | `claude_code` | Default CLI provider |
| `AGENT_FORGE_PROVIDER_TIMEOUT` | `300` | Provider execution timeout (seconds) |

## Tests

```bash
PYTHONPATH=. python -m pytest api/tests/ -v
```

180+ tests covering routes, services, repositories, executor, and WebSocket events.

## Project structure

```
api/
├── main.py              # FastAPI app, lifespan, CORS
├── config.py            # Settings via pydantic-settings
├── models/              # Pydantic request/response models
├── routes/              # HTTP endpoints (agents, runs, projects, health)
├── services/            # Business logic (agent_service, execution_service)
├── engine/
│   ├── providers.py     # CLI subprocess executor (config-driven)
│   └── executor.py      # Agent execution orchestrator
├── persistence/
│   ├── database.py      # SQLite + WAL setup
│   └── repositories.py  # CRUD operations
├── websocket/           # Real-time event broadcasting
├── tests/               # pytest suite
├── docs/                # API docs, wireframes, containerization plan
└── requirements.txt     # Python dependencies
```

## Key dependencies

| Package | Version | Purpose |
|---|---|---|
| FastAPI | >= 0.115 | Web framework |
| uvicorn | >= 0.34 | ASGI server |
| aiosqlite | >= 0.20 | Async SQLite |
| pydantic | >= 2.10 | Data validation |
| pydantic-settings | >= 2.7 | Env-based config |
| PyYAML | >= 6.0 | Provider config parsing |
| websockets | >= 14.0 | WebSocket support |

## Provider configuration

CLI providers are defined in `providers.yaml` at the project root. Adding a new provider (codex, aider, gemini, etc.) usually requires only a YAML entry if the CLI output matches an existing parser family:

```yaml
providers:
  claude_code:
    command: claude
    args: ["-p", "{{prompt}}", "--dangerously-skip-permissions", "--output-format", "json"]
    timeout: 300
```

See [PROVIDER_PARSER_GUIDE.md](../PROVIDER_PARSER_GUIDE.md) for:
- available `stream_parser` families
- `streaming` command rewrite rules
- when a new provider needs code vs YAML only

See [CONTAINERIZATION.md](docs/CONTAINERIZATION.md) for future Docker deployment plans.

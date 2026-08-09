# Vadgr API

REST + WebSocket backend for the run lifecycle: take a task, start a run, drive the loop, record the outcome. Cross-platform: Windows, macOS and Linux.

## Requirements

- **Python >= 3.12**

### Install Python

```bash
# Ubuntu/Debian
sudo apt-get install python3.12 python3.12-venv

# macOS (Homebrew)
brew install python@3.12

# Windows
# Download from https://www.python.org/downloads/
```

### Providers

A run executes on the provider named in `providers.yaml`. The default is the
in-process native loop; the legacy subprocess providers shell out to an
external CLI, which must then be on your PATH and authenticated.

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

The machine's default provider and model are `providers.yaml`'s, not environment variables.
| `AGENT_FORGE_PROVIDER_TIMEOUT` | `300` | Provider execution timeout (seconds) |

## Tests

```bash
PYTHONPATH=. python -m pytest api/tests/ -v
```

Covers routes, the run lifecycle, the repository, the schema migration and the WebSocket frames.

## Project structure

```
api/
├── main.py              # FastAPI app and lifespan
├── config.py            # Settings via pydantic-settings
├── models/              # Pydantic request/response models
├── routes/              # HTTP endpoints, health, and the two sockets
├── services/            # Run lifecycle, computer-use setup
├── auth/                # Pairing, devices, the two gates
├── transport/           # Loopback and Tailscale adapters
├── engine/
│   ├── providers.py     # Provider config and the subprocess bridge
│   └── native_bridge.py # The native loop behind that interface
├── persistence/
│   ├── database.py      # SQLite, WAL setup and the schema migration
│   └── repositories.py  # Run storage
├── websocket/           # Real-time event broadcasting
├── tests/               # pytest suite
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

Providers are defined in `providers.yaml` at the project root, along with the machine's `default_provider`. Adding a legacy CLI provider usually requires only a YAML entry if its output matches an existing parser family:

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

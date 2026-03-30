# CLI - Command-Line Interface

Unified CLI for Agent Forge. Manages agents, runs, registry, computer use, and services from the terminal.

## Setup

```bash
python3 -m venv cli/.venv
cli/.venv/bin/pip install -r cli/requirements.txt
```

## Usage

```bash
PYTHONPATH=. cli/.venv/bin/python -m cli <command>
```

Or via the `forge` wrapper (installed by setup.sh):

```bash
forge <command>
```

## Commands

### Services

```
forge start [--api-port N] [--frontend-port N]
forge stop
forge restart
forge status
forge logs [--service api|frontend] [--no-follow]
forge update
forge api [--port N]
```

### Agents

```
forge ps
forge agents list
forge agents get <id-or-name>
forge agents create --name "..." --description "..."
forge agents update <id-or-name> [--name "..."] [--description "..."]
forge agents delete <id-or-name>
forge agents export <id-or-name> [-o output.agnt]
forge agents import <file.agnt>
```

Short IDs from `forge ps` and partial names both work. For example `forge agents get 654e` or `forge agents get linkedin`.

### Running agents

```
forge run <name-or-id>                          # interactive, prompts for inputs
forge run <name-or-id> --input key=value        # non-interactive
forge run <name-or-id> --background             # skip progress streaming
forge run <name-or-id> --provider codex --model gpt-5.4
```

When run interactively, the CLI prompts for each input field. File inputs are uploaded to the API automatically. The CLI streams step progress via WebSocket and shows results when done:

```
[forge] Run started: abc123
  Step 1: Analyze Data              done (1m 23s)
  Step 2: Generate Report           done (45s)
[forge] Run completed (2m 8s)

  See results: http://localhost:3000/runs/abc123
```

Ctrl+C cancels the run.

### Runs

```
forge runs list [--status running|completed|failed]
forge runs get <run-id>
forge runs cancel <run-id>
forge runs approve <run-id>
forge runs logs <run-id>
```

### Computer use

```
forge computer-use enable     # starts daemon, writes MCP configs
forge computer-use disable    # stops daemon, removes MCP configs
forge computer-use status     # shows enabled state and daemon health
```

The daemon runs natively on Windows (WSL2 only) and persists across `forge start/stop`. It starts when you enable computer use and stops when you disable it.

### Registry

```
forge registry pack <folder> [-o output.agnt]
forge registry pull <name> [--force]
forge registry push <file.agnt>
forge registry search <query>
forge registry agents
forge registry serve [--port 9876] [--dir ./data] [--token secret]
forge registry add <name> --type github|http|local [--url ...] [--path ...]
forge registry use <name>
forge registry list
forge registry remove <name>
```

### Info

```
forge health
forge providers
```

## Architecture

Service commands (start, stop, status, logs) manage OS processes directly. Everything else talks to the API over HTTP. Registry commands call the registry module directly (no API needed).

| Command group | Backend |
|---|---|
| start/stop/status/logs | Direct process management |
| agents, runs, health, providers | HTTP to API at localhost:8000 |
| computer-use | HTTP to API (API manages daemon) |
| registry (pack/pull/push/search) | Direct filesystem / registry module |

## Tests

```bash
# Unit tests (no API needed)
PYTHONPATH=. cli/.venv/bin/python -m pytest cli/tests/ -k "not test_cli"

# CLI tests with fake API server (CI-safe, no LLM)
PYTHONPATH=. cli/.venv/bin/python -m pytest cli/tests/test_cli.py

# All CLI tests
PYTHONPATH=. cli/.venv/bin/python -m pytest cli/tests/
```

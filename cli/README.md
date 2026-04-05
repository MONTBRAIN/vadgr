# CLI - Command-Line Interface

Unified CLI for Vadgr. Manages agents, runs, registry, computer use, and services from the terminal.

## Setup

```bash
python3 -m venv cli/.venv
cli/.venv/bin/pip install -r cli/requirements.txt
```

## Usage

```bash
PYTHONPATH=. cli/.venv/bin/python -m cli <command>
```

Or via the `vadgr` wrapper (installed by setup.sh):

```bash
vadgr <command>
```

## Commands

### Services

```
vadgr start [--api-port N] [--frontend-port N]
vadgr stop
vadgr restart
vadgr status
vadgr logs [--service api|frontend] [--no-follow]
vadgr update
vadgr api [--port N]
```

### Agents

```
vadgr ps
vadgr agents list
vadgr agents get <id-or-name>
vadgr agents create --name "..." --description "..."
vadgr agents update <id-or-name> [--name "..."] [--description "..."]
vadgr agents delete <id-or-name>
vadgr agents export <id-or-name> [-o output.agnt]
vadgr agents import <file.agnt>
```

Short IDs from `vadgr ps` and partial names both work. For example `vadgr agents get 654e` or `vadgr agents get linkedin`.

### Running agents

```
vadgr run <name-or-id>                          # interactive, prompts for inputs
vadgr run <name-or-id> --input key=value        # non-interactive
vadgr run <name-or-id> --background             # skip progress streaming
vadgr run <name-or-id> --provider codex --model gpt-5.4
```

When run interactively, the CLI prompts for each input field. File inputs are uploaded to the API automatically. The CLI streams step progress via WebSocket and shows results when done:

```
[vadgr] Run started: abc123
  Step 1: Analyze Data              done (1m 23s)
  Step 2: Generate Report           done (45s)
[vadgr] Run completed (2m 8s)

  See results: http://localhost:3000/runs/abc123
```

Ctrl+C cancels the run.

### Runs

```
vadgr runs list [--status running|completed|failed]
vadgr runs get <run-id>
vadgr runs cancel <run-id>
vadgr runs approve <run-id>
vadgr runs logs <run-id>
```

### Computer use

```
vadgr computer-use enable     # starts daemon, writes MCP configs
vadgr computer-use disable    # stops daemon, removes MCP configs
vadgr computer-use status     # shows enabled state and daemon health
```

The daemon runs natively on Windows (WSL2 only) and persists across `vadgr start/stop`. It starts when you enable computer use and stops when you disable it.

### Registry

```
vadgr registry pack <folder> [-o output.agnt]
vadgr registry pull <name> [--force]
vadgr registry push <file.agnt>
vadgr registry search <query>
vadgr registry agents
vadgr registry serve [--port 9876] [--dir ./data] [--token secret]
vadgr registry add <name> --type github|http|local [--url ...] [--path ...]
vadgr registry use <name>
vadgr registry list
vadgr registry remove <name>
```

### Info

```
vadgr health
vadgr providers
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

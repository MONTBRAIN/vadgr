# CLI - Command-Line Interface

Unified CLI for Agent Forge. Manages agents, runs, registry, and system info from the terminal.

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

### Agents

```
forge ps                                    # list agents
forge agents list                           # same as ps
forge agents get <id>                       # show agent details
forge agents create --name "..." --description "..."
forge agents delete <id>
forge run <name-or-id> [--input key=value]  # run an agent
```

### Runs

```
forge runs list [--status failed]
forge runs get <run-id>
forge runs cancel <run-id>
forge runs approve <run-id>
forge runs logs <run-id>
```

### Registry

```
forge registry pack <folder>               # package agent to .agnt
forge registry pull <name>                 # install from registry
forge registry push <file.agnt>            # publish to registry
forge registry search <query>              # search registries
forge registry agents                      # list installed agents
forge registry serve [--port 9876]         # self-hosted registry server
```

### Info

```
forge health                               # API health check
forge providers                            # list providers + models
```

## Architecture

Service commands (`start`, `stop`, `status`, `logs`) stay in the bash wrapper since the API may be down. Everything else delegates to this Python CLI module.

| Command group | How it talks to the backend |
|---|---|
| agents, runs, health, providers | HTTP to API at localhost:8000 |
| registry (pack, pull, push, search) | Direct import of `registry` module |
| service (start, stop, status, logs) | Bash process management |

## Tests

```bash
# Unit tests (no API needed)
PYTHONPATH=. cli/.venv/bin/python -m pytest cli/tests/ -k "not integration"

# Integration tests (requires API at localhost:8000)
PYTHONPATH=. cli/.venv/bin/python -m pytest cli/tests/test_integration.py

# All tests
PYTHONPATH=. cli/.venv/bin/python -m pytest cli/tests/
```

# Containerization Plan

Future Docker setup for Agent Forge. Not yet implemented -- this document captures the architecture decisions.

## Problem

CLI agent tools (Claude Code, Codex, Aider, etc.) authenticate on the host machine. For example, Claude Code uses `claude auth` which stores OAuth tokens in `~/.claude/` -- these tokens may need browser-based refresh that doesn't exist in containers. Other tools have similar host-specific auth. Running these tools inside Docker is fragile.

## Architecture: Split Worker

```mermaid
graph TB
    subgraph Docker["Docker (stateless)"]
        FE["frontend<br/>nginx + React"]
        API["api<br/>FastAPI + uvicorn<br/>Routes, DB, WebSocket"]
        FE -->|"/api, /ws"| API
    end

    subgraph Host["Host (native)"]
        Worker["worker.py<br/>Polls DB for jobs<br/>Runs CLI agent tool<br/>Writes results"]
        CU["computer_use/<br/>Desktop automation"]
        Forge["forge/<br/>Prompt templates"]
        Output["output/<br/>Generated agents"]
    end

    DB[("data/agent_forge.db<br/>SQLite + WAL")]

    API -->|"bind mount"| DB
    Worker -->|"read/write"| DB
    Worker -->|"subprocess"| Claude["CLI Agent Tool<br/>(host auth)<br/>claude / codex / aider"]
    Worker -->|"reads"| Forge
    Worker -->|"writes"| Output

    User((User)) -->|"http://localhost:3000"| FE
```

### Docker services (frontend + API server)

- **frontend**: Multi-stage build (Node build -> nginx). Serves the React app and reverse-proxies `/api` and `/ws` to the API container.
- **api**: Python 3.12 slim. Runs FastAPI with uvicorn. Handles HTTP routes, WebSocket, and DB operations. Does NOT run Claude Code -- just writes run records with status `queued`.

### Host processes

- **worker.py**: Simple polling loop. Watches the SQLite DB for runs with status `queued`, picks them up, executes via the locally-authenticated CLI agent tool (claude, codex, aider, etc.), writes results back. ~60 lines of Python.
- **computer_use/**: Desktop automation engine. Runs natively -- needs host display, mouse, keyboard access.

### Communication

The SQLite database (bind-mounted from host into the API container) is the only communication channel. No message queues, no RPC, no extra infrastructure.

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant API as API (Docker)
    participant DB as SQLite (host)
    participant Worker as Worker (host)
    participant CLI as CLI Agent Tool

    User->>Frontend: Click "Start Run"
    Frontend->>API: POST /api/agents/{id}/run
    API->>DB: INSERT run (status: queued)
    API-->>Frontend: 202 {run_id, status: queued}

    loop Every 2s
        Worker->>DB: SELECT ... WHERE status = 'queued'
        DB-->>Worker: run record
    end

    Worker->>DB: UPDATE status = 'running'
    Worker->>CLI: execute prompt (subprocess)
    CLI-->>Worker: JSON result
    Worker->>DB: UPDATE status = 'completed', outputs = result

    loop Auto-refresh
        Frontend->>API: GET /api/runs/{id}
        API->>DB: SELECT run
        DB-->>API: run record
        API-->>Frontend: {status: completed, outputs: ...}
    end

    Frontend-->>User: Display results
```

SQLite WAL mode (already enabled) handles concurrent reads/writes from container + host.

### Bind mounts

```yaml
volumes:
  - ./data:/app/data              # SQLite DB
  - ./forge:/app/forge:ro         # Prompt templates (read-only in container)
  - ./output:/app/output          # Generated agent files
  - ./providers.yaml:/app/providers.yaml:ro
```

### Credentials

Vadgr invokes providers through their CLI binaries (`claude`, `codex`, `gemini`), which handle their own authentication. The current path is:

- The user runs `claude login` / `codex login` / `gemini auth` on the host. The host worker inherits that session from `~/.claude/` / `~/.codex/` / `~/.gemini/`. Nothing in vadgr reads or injects a provider API key.

If a future Docker deployment ever needs non-interactive auth, the CLIs do each support their vendor's API-key env var as a fallback, but that is not the primary path and is not required for normal use.

### User experience

```bash
git clone https://github.com/santiagomd11/Agent-Forge.git
cd Agent-Forge
docker compose up -d          # frontend + API
python worker.py              # uses local claude auth
# Open http://localhost:3000
```

## Why not CLI agent tools in Docker?

CLI agent tools authenticate on the host:
- Claude Code stores OAuth tokens in `~/.claude/` that may need browser-based refresh
- Codex/Aider/others store API keys or configs in host-specific locations
- Mounting auth directories into containers is fragile and platform-dependent (`~` resolves differently on Windows, Mac, Linux)

The worker approach avoids this entirely -- tools run where they were installed and authenticated.

## Why not Anthropic's Xvfb approach for computer use?

Anthropic's computer-use-demo runs a virtual Linux desktop (Xvfb) inside Docker. This:
- Only controls Linux apps inside the container, not the host OS
- Cannot interact with the user's real browser, apps, or files
- Is a sandbox, not a real desktop automation tool

Agent Forge's computer_use engine controls the actual host -- real mouse, real keyboard, real screen across Windows, macOS, Linux, and WSL2. This cross-platform native access requires host execution, not containerization.

## Implementation checklist

- [ ] `api/Dockerfile` -- Python 3.12 slim, pip install requirements, copy api/ code
- [ ] `frontend/Dockerfile` -- Multi-stage: node build, nginx serve
- [ ] `frontend/nginx.conf` -- Reverse proxy /api and /ws to api container
- [ ] `docker-compose.yml` -- Two services, bind mounts, env vars
- [ ] `worker.py` -- Host-side execution worker (~60 lines)
- [ ] `.dockerignore` -- Exclude node_modules, .venv, data/, .git
- [ ] Update README with `docker compose up` instructions

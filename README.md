<p align="center">
  <img src="docs/pet.svg" alt="Pet" height="160" style="image-rendering: pixelated;">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/NameLigth.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/NameDark.svg">
    <img src="docs/NameDark.svg" alt="VADGR" height="160">
  </picture>
</p>

<p align="center">
  <img src="docs/line.svg" alt="Separator" width="100%", heigth = 20px>
</p>


<p align="center">
  <i><b>Independent agents that can operate on any task, no matter how complex.</b></i>
</p>

Vadgr gives AI agents the ability to think through problems (forge) and interact with the real world (computer use). Each module works on its own or together with the others. Cross-platform: runs on Windows, Linux, and macOS (Work progres).


##  Paltform

<div align="left">

|  | Technology | Status | Role |
|:---:|:---:|:---:|:---|
| <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/linux/linux-original.svg" width="25" /> | Linux | Stable | Primary platform |
| <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/windows8/windows8-original.svg" width="25" /> | Windows / WSL2 | Stable | Supported platform |
| <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/apple/apple-original.svg" width="25" /> | macOS | WIP | Work in progress |

</div>

## Install

Works on **Linux**, **WSL**, and **Windows**. macOS support is in progress (agent creation and CLI steps work, computer use does not). The installer sets up everything: git, Python, Node.js, dependencies, and the `vadgr` CLI.

```bash
# Linux / macOS / WSL
curl -fsSL https://raw.githubusercontent.com/MONTBRAIN/Agent-Forge/master/setup.sh | bash
```

```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/MONTBRAIN/Agent-Forge/master/setup.ps1 | iex
```

Then install at least one CLI agent tool:

```bash
# Pick one (or add your own to providers.yaml)
curl -fsSL https://claude.ai/install.sh | bash              # Claude Code (Linux/macOS)
irm https://claude.ai/install.ps1 | iex                    # Claude Code (Windows)
npm install -g @openai/codex                               # Codex
npm install -g @google/gemini-cli                           # Gemini CLI
```

Restart your terminal, then:

```bash
vadgr start
```

### Vadgr CLI

**Services:**

| Command | Description |
|---------|-------------|
| `vadgr start` | Start API and frontend servers |
| `vadgr stop` | Stop all services |
| `vadgr restart` | Restart all services |
| `vadgr status` | Show if services are running |
| `vadgr logs` | Tail API server logs |
| `vadgr update` | Pull latest code and reinstall deps |

**Agents and runs:**

| Command | Description |
|---------|-------------|
| `vadgr ps` | List all agents |
| `vadgr agents list` | List all agents |
| `vadgr agents get <id>` | Show agent details |
| `vadgr agents create --name "..." --description "..."` | Create a new agent |
| `vadgr agents update <id> [--name] [--description]` | Update an agent |
| `vadgr agents delete <id>` | Delete an agent |
| `vadgr agents export <id> [-o file.agnt]` | Export agent as .agnt archive |
| `vadgr agents import <file.agnt>` | Import agent from .agnt archive |
| `vadgr run <name> [--input key=value]` | Run an agent (interactive inputs) |
| `vadgr run <name> --background` | Run without streaming progress |
| `vadgr runs list [--status failed]` | List runs |
| `vadgr runs get <id>` | Show run details |
| `vadgr runs cancel <id>` | Cancel a running run |
| `vadgr runs logs <id>` | Show run logs |

**Info:**

| Command | Description |
|---------|-------------|
| `vadgr health` | Check API health |
| `vadgr providers` | List available providers and models |
| `vadgr computer-use enable` | Enable desktop automation |
| `vadgr computer-use disable` | Disable desktop automation |
| `vadgr computer-use status` | Show computer use and daemon status |

**Registry** -- package manager for agent workflows:

| Command | Description |
|---------|-------------|
| `vadgr registry pack <folder>` | Package agent folder into `.agnt` archive |
| `vadgr registry pull <name>` | Download and install agent from registry |
| `vadgr registry push <file.agnt>` | Publish `.agnt` to a registry |
| `vadgr registry search <query>` | Search registries for agents |
| `vadgr registry serve` | Start a self-hosted registry server |
| `vadgr registry add <name> --type ...` | Add a registry to config |
| `vadgr registry use <name>` | Set active registry |
| `vadgr registry list` | List configured registries |
| `vadgr registry remove <name>` | Remove a registry |

### Manual setup

If you prefer to set things up manually, see [api/README.md](api/README.md) and [frontend/README.md](frontend/README.md).

Provider parser families and real sample log lines are documented in [PROVIDER_PARSER_GUIDE.md](PROVIDER_PARSER_GUIDE.md).

## Architecture

```mermaid
graph LR
    User((User)) -->|":3000"| FE[Frontend<br/>React + Vite]
    FE -->|"REST /api"| API[API Server<br/>FastAPI]
    FE <-->|"WebSocket /ws"| API
    API -->|subprocess| CLI[CLI Agent Tool<br/>claude / codex / aider]
    API -->|read/write| DB[(SQLite)]
    CLI -->|reads| Forge[forge/<br/>Prompt Templates]
    CLI -->|writes| Output[output/<br/>Generated Agents]
    API -.->|"if computer_use"| CU[Computer Use<br/>Desktop Automation]
    CU -->|controls| Desktop[Host OS<br/>Mouse, Keyboard, Screen]
```

## Modules

### [cli/](cli/) - Command-Line Interface

Unified CLI built with Click. Manages agents, runs, registry, and system info. Talks to the API over HTTP for agent/run operations; calls the registry module directly for package management. Each module has its own venv.

### [api/](api/) - REST API + Execution Engine

FastAPI backend for agent CRUD, forge generation, and execution. Calls any CLI agent tool as a subprocess via config-driven providers. See [api/README.md](api/README.md) for setup details.

### [frontend/](frontend/) - Web Dashboard

React 19 + TypeScript + Vite dashboard for managing agents and viewing runs. See [frontend/README.md](frontend/README.md) for setup details.

### [forge/](forge/) - Workflow Generation Engine

Designs and generates complete agentic workflow projects through a 7-step conversational process. Agent-agnostic: works with any AI coding agent that can read files and follow instructions.

### [computer_use/](computer_use/) - Desktop Automation Engine

Captures screenshots, locates UI elements, and executes mouse/keyboard actions across **Windows, macOS, and Linux** (including WSL2). Works as a Python library, MCP server, or CLI tool. Runs natively on the host.

### [registry/](registry/) - Agent Package Manager

Package, publish, and install agent workflows. Supports three backends: GitHub (releases + raw content), any HTTP server, or a local folder. Agents are distributed as `.agnt` archives (zip with manifest). Includes SHA256 integrity verification, SSRF protection, and zip slip prevention.

### paper/ - Research Paper

Academic paper documenting the framework.

## Structure

```
Vadgr/
├── cli/                   # Unified command-line interface
│   ├── main.py            # Root Click group
│   ├── http.py            # HTTP client for API
│   ├── commands/          # agents, runs, registry, info
│   └── tests/             # Unit + integration tests
├── api/                   # REST API + execution engine
│   ├── main.py            # FastAPI app
│   ├── routes/            # HTTP endpoints
│   ├── services/          # Business logic
│   ├── engine/            # CLI provider executor
│   └── persistence/       # SQLite database
├── frontend/              # React web dashboard
│   ├── src/pages/         # Dashboard, Agents, Runs, Settings
│   ├── src/components/    # UI components
│   └── src/hooks/         # TanStack Query hooks
├── forge/                 # Workflow generation engine (standalone)
│   ├── agentic.md         # 7-step orchestrator
│   ├── Prompts/           # Specialized agent prompts
│   ├── patterns/          # 10 reusable workflow patterns
│   └── examples/          # 3 example workflows
├── computer_use/          # Desktop automation engine (standalone)
│   ├── core/              # Engine facade, types, actions
│   ├── platform/          # OS backends (Linux, Windows, macOS, WSL2)
│   └── mcp_server.py      # MCP server
├── registry/              # Agent package manager
│   ├── cli.py             # Click CLI (pack, pull, push, search)
│   ├── security.py        # Zip safety, SSRF, SHA256, TLS
│   ├── server.py          # Self-hosted HTTP registry server
│   └── adapters/          # GitHub, HTTP, local backends
├── providers.yaml         # CLI provider configs (claude, codex, aider, etc.)
├── data/                  # SQLite database (created at runtime)
├── output/                # Generated agent workflows
└── paper/                 # Research paper
```

## Technologies

**Frontend**

<div align="left">

|  | Technology | Version | Role |
|:---:|:---:|:---:|:---|
| <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/react/react-original.svg" width="25" /> | React | 19.2 | UI framework |
| <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/typescript/typescript-original.svg" width="25" /> | TypeScript | 5.9 | Type-safe JavaScript |
| <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/vitejs/vitejs-original.svg" width="25" /> | Vite | 7.3 | Build tool and dev server |
| <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/tailwindcss/tailwindcss-original.svg" width="25" /> | Tailwind CSS | 4.2 | Utility-first CSS framework |
| <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/react/react-original.svg" width="25" style="filter: hue-rotate(140deg);" /> | TanStack Query | 5.90 | Data fetching and state management |
| <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/reactrouter/reactrouter-original.svg" width="25" /> | React Router | 7.13 | Client-side routing |
| <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/vitest/vitest-original.svg" width="25" /> | Vitest | 4.0 | Unit testing framework |
| <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/eslint/eslint-original.svg" width="25" /> | ESLint | 9.39 | Code linting |

</div>

**Backend**

<div align="left">

|  | Technology | Version | Role |
|:---:|:---:|:---:|:---|
| <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/fastapi/fastapi-original.svg" width="25" /> | FastAPI | 0.115 | Web framework |
| <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/python/python-original.svg" width="25" /> | Python | 3.12 | Runtime language |
| <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/sqlite/sqlite-original.svg" width="25" /> | SQLite | 3 | Relational database |
| <img src="https://cdn.simpleicons.org/pydantic/E92063" width="28" /> | Pydantic | 2.10 | Data validation |
| <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/socketio/socketio-original.svg" width="25" /> | WebSockets | 14.0 | Real-time communication |
| <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/pytest/pytest-original.svg" width="25" /> | pytest | 8.0 | Testing framework |

</div>

**Desktop Automation**

<div align="left">

|  | Technology | Version | Role |
|:---:|:---:|:---:|:---|
| <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/python/python-original.svg" width="25" /> | Pillow | 10.0 | Image processing |
| <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/python/python-plain.svg" width="25" /> | mss | 9.0 | Screenshot capture |
| <picture><source media="(prefers-color-scheme: dark)" srcset="https://cdn.simpleicons.org/anthropic/white"><img src="https://cdn.simpleicons.org/anthropic/black" width="25" alt="Anthropic Logo"></picture> | MCP | 1.0 | Standardized tool interface |

</div>

## Contributing

1. Create a branch from `master`:
   ```bash
   git checkout master && git checkout -b feature/your-change
   ```
2. Make your changes and commit:
   ```bash
   git add . && git commit -m "your message"
   ```
3. Push and open a PR into `master`:
   ```bash
   git push -u origin feature/your-change
   ```


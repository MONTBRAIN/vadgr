# Vadgr Registry -- Design Document

## Overview

A platform-agnostic agent registry for Vadgr. Authors package agents as
`.agnt` files, publish them to registries, and users pull them with a single
command. Anyone can host their own registry.

A registry is any source that serves an `index.json` and `.agnt` files -- GitHub
repo, static file server, S3 bucket, local folder, or any HTTP server.

## Registry Protocol

Three endpoints define a registry:

```
GET  /index.json              -- agent catalog
GET  /agents/{name}.agnt      -- download an agent
POST /agents/{name}.agnt      -- upload an agent (optional)
```

### index.json Format

```json
{
  "registry": {
    "name": "forge-official"
  },
  "agents": {
    "research-paper": {
      "version": "0.1.0",
      "description": "Generates a research paper from a topic",
      "author": "montbrain",
      "download_url": "agents/research-paper-0.1.0.agnt"
    }
  }
}
```

`download_url` can be relative (resolved against registry URL) or absolute.

## .agnt Format

A zip archive with custom extension:

```
manifest.json           # required -- agent metadata
agentic.md              # required -- workflow orchestrator
CLAUDE.md               # optional
README.md               # optional
agent/
    steps/              # step_NN_name.md files
    Prompts/            # specialized agent prompts
    scripts/            # utility scripts
```

### manifest.json

```json
{
  "manifest_version": 1,
  "name": "research-paper",
  "version": "0.1.0",
  "description": "Generates a research paper from a topic",
  "author": "",
  "provider": "claude_code",
  "computer_use": false,
  "steps": [
    {"name": "Research", "computer_use": false},
    {"name": "Write Draft", "computer_use": false}
  ]
}
```

Required: `manifest_version`, `name`. Everything else optional with defaults.

## CLI Commands

```bash
forge pack ./my-agent/        # folder -> .agnt
forge pull agent-name         # download + install from registry
forge push my-agent.agnt      # publish to registry
forge search "data analysis"  # search registries
forge agents                  # list installed agents
```

## Adapter Architecture

Three backend adapters, same interface:

| Adapter | GET (pull) | POST (push) |
|---------|-----------|-------------|
| Local   | Read from filesystem | Copy file + update index.json |
| HTTP    | HTTP GET | HTTP POST with auth token |
| GitHub  | raw.githubusercontent.com | GitHub Releases API + Contents API |

## Config (~/.forge/registry.yaml)

```yaml
registries:
  - name: official
    url: https://raw.githubusercontent.com/MONTBRAIN/sample-registry/main
    type: github
    github_repo: MONTBRAIN/sample-registry
    default: true
  - name: local
    path: ~/my-agents
    type: local
agents_dir: ~/.forge/agents
```

## Module Structure

```
registry/
    __init__.py
    __main__.py            # python -m registry entry point
    cli.py                 # Click CLI (5 commands)
    config.py              # Config loading, paths, constants
    manifest.py            # Pydantic manifest model + validation
    packer.py              # Pack/unpack .agnt archives
    installer.py           # Install/uninstall/list agents
    registry_client.py     # High-level operations orchestrating adapters
    adapters/
        __init__.py        # Factory: create_adapter()
        base.py            # Abstract base (fetch_index, download, push, search)
        github.py          # GitHub Releases + Contents API
        http.py            # Generic HTTP server
        local.py           # Local filesystem
    tests/                 # 96 tests
    docs/
        PLAN.md            # This file
    HANDOFF.md             # Session handoff for continuity
```

## Implementation Status

### Phase 1 (Alpha) -- DONE
- .agnt packer/unpacker with manifest validation
- Local, HTTP, and GitHub adapters
- Click CLI with pack, pull, push, search, agents
- Wired into forge bash script
- 96 tests passing

### Phase 2 (Future)
- Registry server (FastAPI) for self-hosted registries
- Version resolution (@latest, @^1.0.0)
- forge update command for installed agents
- Frontend marketplace page
- Download counters
- Agent signing (GPG/SSH keys)
- Community ratings

### Phase 3 (Future)
- Multi-registry search with priority ordering
- Private registry auth (token-based)
- GitHub Action for automated validation on publish
- Agent dependency resolution

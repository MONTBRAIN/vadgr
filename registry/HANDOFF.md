# Registry Module Handoff

## Status: REGISTRY DONE + BUG FIXES IN PROGRESS

### Completed
- registry/ module: 13 source files, 96 tests, all passing
- CLI wired into forge bash script (pack/pull/push/search delegate to python -m registry)
- E2E verified: pack -> push -> search -> pull -> agents cycle works with local registry
- CLAUDE.md + setup.sh updated
- Bug fix: approval gate now actually resumes execution (was a no-op)
- Bug fix: AgentRepository.update() whitelists field names
- Bug fix: provider is_available() catches PermissionError/OSError
- Total tests: 1,173 (394 API + 96 registry + 683 computer_use)

### Also Fixed
- forge stop not killing frontend (PID mismatch from npm fork -- switched to npx vite)
- Registry commands added to forge help text

### Remaining Bugs Found (not fixed yet -- lower priority)
- Desktop step 30s threshold is hardcoded, could fail on fast/slow systems
- Skip-phrase detection in executor is easily bypassed by different wording
- JSON parsing fallback in executor doesn't log when it falls back to text
- Subprocess timeout in providers.py doesn't always clean up zombie processes
- DAG runner doesn't validate agent_id references exist before execution
- Database migration errors silently ignored in database.py
- Path traversal possible via symlinks in output resolution (theoretical)

## Branch: feat/registry-cli

## What We're Building

A package manager for Agent Forge agents. Users package workflows as `.agnt` files, push them to registries, and pull them with a single command.

## CLI Commands (use `forge` name, NOT `ryve` -- ryve was taken)

| Command | What it does |
|---------|-------------|
| `forge pack ./folder` | Package agent folder into `.agnt` (zip + manifest.json) |
| `forge pull agent-name` | Download + install from registry to `~/.forge/agents/` |
| `forge push file.agnt` | Upload to registry |
| `forge search query` | Search registry index.json |
| `forge agents` | List installed agents (extend existing command) |

## Architecture

Registry protocol (npm-style, NOT GitHub-coupled):
```
GET  /index.json              -- list all agents
GET  /agents/{name}.agnt      -- download an agent
POST /agents/{name}.agnt      -- upload an agent
```

Three adapters:
- **GitHub**: GET via raw.githubusercontent.com, POST via Releases API
- **HTTP**: Any server implementing the 3 endpoints above
- **Local folder**: file:// path, direct filesystem operations

## Module Structure

```
registry/
    __init__.py
    __main__.py            # python -m registry entry point
    cli.py                 # Click command group
    config.py              # ~/.forge/registry.yaml, constants, paths
    manifest.py            # Manifest pydantic model + validation
    packer.py              # folder -> .agnt zip
    installer.py           # .agnt -> ~/.forge/agents/{name}/
    registry_client.py     # Base client + adapter pattern
    adapters/
        __init__.py
        github.py          # GitHub registry adapter
        http.py            # Generic HTTP registry adapter
        local.py           # Local folder adapter
    server.py              # Simple FastAPI registry server (self-hosted)
    tests/
        __init__.py
        conftest.py
        test_manifest.py
        test_packer.py
        test_installer.py
        test_registry_client.py
        test_cli.py
    docs/
        PLAN.md            # Full design doc
```

## Key Decisions

- CLI framework: Click (add to api/requirements.txt)
- Config location: ~/.forge/registry.yaml (alongside existing .forge installation)
- Installed agents: ~/.forge/agents/{name}/
- HTTP client: urllib.request (stdlib, no new deps)
- .agnt format: zip with manifest.json at root + agent folder contents
- Excluded from .agnt: __pycache__, .git, .venv, node_modules, output/
- manifest.json required fields: manifest_version, name
- Entry point: setup.sh generates ~/.forge/bin/forge wrapper delegates pack/pull/push/search to python -m registry

## manifest.json Schema

```json
{
  "manifest_version": 1,
  "name": "research-paper",
  "version": "0.1.0",
  "description": "...",
  "author": "",
  "provider": "claude_code",
  "computer_use": false,
  "steps": [{"name": "Step Name", "computer_use": false}]
}
```

## index.json Format

```json
{
  "registry": {"name": "forge-official"},
  "agents": {
    "research-paper": {
      "version": "0.1.0",
      "description": "...",
      "author": "montbrain",
      "download_url": "https://github.com/.../research-paper-0.1.0.agnt"
    }
  }
}
```

## Config (~/.forge/registry.yaml)

```yaml
registries:
  - name: official
    url: https://raw.githubusercontent.com/MONTBRAIN/forge-registry/main
    type: github
    github_repo: MONTBRAIN/forge-registry
    default: true
  - name: local
    path: ~/my-agents
    type: local
agents_dir: ~/.forge/agents
```

## Implementation Order

1. config.py -- constants, paths, config loading
2. manifest.py + tests -- Pydantic model, validation
3. packer.py + tests -- folder -> .agnt
4. installer.py + tests -- .agnt -> ~/.forge/agents/
5. adapters/ + tests -- GitHub, HTTP, local
6. registry_client.py + tests -- orchestrates adapters
7. cli.py + __main__.py + tests -- Click commands
8. server.py -- simple FastAPI registry server
9. Update api/requirements.txt, setup.sh, CLAUDE.md

## After Registry: Keep Working All Night

When registry module is done, DON'T STOP. Continue improving the product:

### Use Computer Use MCP for E2E Testing
You have access to the computer use MCP server. Use it to:
- Open a browser and navigate to http://localhost:3000 (the forge frontend)
- Create agents, run them, verify the UI works
- Take screenshots to see what's happening
- Click buttons, fill forms, test the full user flow
- Test with different providers (claude_code, codex, gemini)

MCP tools available: `mcp__computer_use__screenshot`, `mcp__computer_use__click`,
`mcp__computer_use__type_text`, `mcp__computer_use__key_press`, `mcp__computer_use__scroll`

### Bug Hunting Priority
- Run agents E2E and see if they complete correctly
- Test the step failure validation (desktop steps should fail if <30s)
- Test cancel/pause during runs
- Check error messages in the frontend -- are they helpful?
- Test edge cases: empty inputs, missing files, bad configs
- Check api/engine/executor.py error handling paths
- Test api/engine/providers.py with different provider configs
- Verify computer use toggle works (enable/disable from frontend)

### Use the API Directly
You can also test via the REST API:
- `curl http://localhost:8000/api/agents` -- list agents
- `curl http://localhost:8000/api/settings/computer-use` -- check CU status
- `curl http://localhost:8000/api/runs` -- list runs
- Create agents, trigger runs, check outputs via API

### What to Fix
- Any bugs found during testing
- Error handling gaps
- UI issues visible in screenshots
- Missing validations
- Anything that would break a first-time user's experience

### Rules
- Commit fixes locally on separate branches (don't mix with registry branch)
- Don't push anything
- Document findings in this file or in commit messages

## CLI Strategy

The existing `forge` CLI is a bash script in setup.sh (start, stop, agents, etc.).
Decision: **keep the bash script as-is, add registry commands via Click as a separate
entry point that the bash script delegates to**.

The bash `forge` script will add cases for `pack`, `pull`, `push`, `search` that
call `python -m registry <command>`. This avoids rewriting the working bash CLI
while adding the new registry features cleanly.

Eventually the entire CLI can migrate to Click, but NOT for alpha.

## How to Continue (Survival Strategy)

**IMPORTANT**: Monitor context usage. When context is getting large (~80%+),
you MUST spawn a new session before dying. The survival mechanism uses the
computer use MCP server.

### Steps to survive:

1. Update this HANDOFF.md with current progress (what's done, what's next)
2. Commit all work locally (git add + git commit, NO push)
3. Use computer use MCP to open a new WSL terminal:
   - Call `mcp__computer_use__screenshot` to see the desktop
   - Call `mcp__computer_use__key_press` with `ctrl+shift+t` (or equivalent) to open terminal
   - Type the commands below using `mcp__computer_use__type_text`
4. In the new terminal, start a fresh Claude session:

```bash
cd /home/santiago/MakeHistory/Agent-Forge
claude --dangerously-skip-permissions
```

5. Tell the new session:
```
Read registry/HANDOFF.md and continue where the previous session left off.
Branch is feat/registry-cli. Don't push. Run tests as you go. User is asleep.
```

### If computer use is not available:

Just commit everything, update HANDOFF.md with progress, and stop gracefully.
Santiago will continue in the morning.

## Files Already on Disk

Check `git status` and `git diff --stat` to see what's been created so far.
The implementation follows TDD -- tests written alongside or before implementation code.

## Development Approach: STRICT TDD

Follow TDD for every module:
1. Write tests FIRST
2. Run tests -- confirm they FAIL (red)
3. Write the minimum implementation to pass
4. Run tests -- confirm they PASS (green)
5. Refactor if needed
6. Move to next module

DO NOT write implementation code without tests already written.
DO NOT skip the red phase -- if tests pass before implementation, they're bad tests.

## Important Rules (from Santiago)

- No "Co-Authored-By" lines in commits
- No emoji in generated content
- Commit locally but do NOT push (Santiago will review and push)
- Always write unit tests for new code
- SOLID principles, named constants over hardcoded values
- Research before implementing
- Keep `forge` as CLI name (not ryve -- name was taken)
- Branch: feat/registry-cli (based on master with all merged fixes)

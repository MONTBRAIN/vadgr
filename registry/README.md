# Registry - Agent Package Manager

Package, publish, and install Vadgr workflows as `.agnt` archives. Supports GitHub, HTTP, and local filesystem backends.

## Setup

```bash
python3 -m venv registry/.venv
registry/.venv/bin/pip install -r registry/requirements.txt
```

Note: the registry is typically used via the CLI (`forge registry <command>`). Direct usage is for library consumers or testing.

## Backends

### GitHub

Uses GitHub Releases for file storage and the repo's `index.json` for the catalog. No server needed.

```yaml
# ~/.forge/registry.yaml
registries:
  - name: official
    type: github
    url: https://raw.githubusercontent.com/MONTBRAIN/sample-registry/master
    github_repo: MONTBRAIN/sample-registry
```

### HTTP

Any server implementing three endpoints: `GET /index.json`, `GET /agents/{name}.agnt`, `POST /agents/{name}.agnt`.

```yaml
registries:
  - name: company
    type: http
    url: https://registry.mycompany.com
    token: $REGISTRY_TOKEN
```

### Local

A folder on disk. Works with synced folders (Dropbox, Drive) for simple team sharing.

```yaml
registries:
  - name: local
    path: ~/my-agents
    type: local
```

## .agnt Format

A zip archive containing:
- `manifest.json` -- name, version, description, steps, provider
- Agent files -- `agentic.md`, `agent/steps/`, `agent/Prompts/`, etc.

## Security

- SHA256 integrity: hash computed on push, verified on pull
- Zip slip prevention: path traversal, absolute paths, symlinks blocked
- Zip bomb protection: max 500MB uncompressed, max 5000 files
- SSRF protection: private IPs and non-HTTP schemes blocked on download
- TLS 1.2+ enforced on all HTTPS connections
- Token env var support: `$VAR` or `${VAR}` syntax in config

## Self-Hosted Server

```bash
forge registry serve --port 9876 --dir ./my-registry --token my-secret
```

Implements the full registry protocol with Bearer token auth and SHA256 upload verification.

## Tests

```bash
PYTHONPATH=. registry/.venv/bin/pip install pytest
PYTHONPATH=. registry/.venv/bin/python -m pytest registry/tests/
```

150 tests covering manifest validation, packing, installation, all adapters, CLI commands, and 54 security tests.

# CLI - Command-Line Interface

**The CLI has been rewritten in Rust**, in [../rust/](../rust/), with the same
commands, arguments and exit codes. Like the Rust daemon beside it, the new CLI
is built from the checkout while the rewrite is in progress: **`setup.sh` still
installs this Python one**, and the swap happens at the `0.4.9` cutover, when
the Python tree leaves. This package is documented here for anyone working on
that transition.

Starts runs, watches them, and manages computer use and the daemon from the
terminal.

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
vadgr start [--api-port N]
vadgr stop
vadgr restart
vadgr status
vadgr logs [--no-follow]
vadgr update
vadgr api [--port N]     # the same command as `vadgr start`
```

### Running work

```
vadgr run "<task>"                              # start it and watch it
vadgr run "<task>" --background                 # start it and return
vadgr run "<task>" --json                       # print the run row as JSON
vadgr run "<task>" --provider codex --model gpt-5.4
```

`--provider` and `--model` go together: one without the other is a usage error
rather than a half-resolved run. With neither, the Rust daemon takes its
default from `machine_settings`. The still-default Python daemon keeps its
legacy `providers.yaml` behavior until the cutover.

### Providers and models

```
vadgr provider login [openai|gemini|anthropic]
vadgr provider status [--refresh] [provider]
vadgr provider logout <provider>
vadgr model list
vadgr model default [provider/model]
```

OpenAI offers ChatGPT browser sign-in or an API key. Gemini and Anthropic move
directly to a hidden API-key prompt when no documented environment key is set.
Connections are additive. Login does not remove another provider or change an
existing default, and it never starts pairing.

The CLI follows the run over a WebSocket and reports the outcome:

```
[vadgr] Run started: abc123
[vadgr] Run completed (2m 8s)

  See results: http://127.0.0.1:8000/api/runs/abc123
```

Exit codes: `0` completed, `1` failed, `2` usage, `3` daemon unreachable, and
`130` on Ctrl-C. **Ctrl-C stops watching and leaves the run going**: an
unattended batch is the point, so stopping one is `vadgr runs cancel`, which
says so.

### Runs

```
vadgr runs list [--status running|completed|failed]
vadgr runs get <run-id>
vadgr runs cancel <run-id>
vadgr runs resume <run-id>
```

Partial run ids work: `vadgr runs get 654e`.

### Computer use

```
vadgr computer-use enable     # enables the daemon-owned cua setting
vadgr computer-use disable    # disables the daemon-owned cua setting
vadgr computer-use status     # shows enabled state and daemon health
```

These commands do not install a runtime and do not edit another client's MCP
configuration. The Rust daemon discovers the installed `vadgr-cua` executable
when it needs desktop automation.

### Info

```
vadgr health
vadgr providers
```

## Architecture

Service commands (start, stop, status, logs) manage OS processes directly. Everything else talks to the API over HTTP.

| Command group | Backend |
|---|---|
| start/stop/status/logs | Direct process management |
| run, runs, health, providers, provider, model, pair | HTTP to the selected API |
| run (watching) | WebSocket to API |
| computer-use | HTTP to API (API manages daemon) |

## Tests

```bash
# Unit tests (no API needed)
PYTHONPATH=. cli/.venv/bin/python -m pytest cli/tests/ -k "not test_cli"

# CLI tests with fake API server (CI-safe, no LLM)
PYTHONPATH=. cli/.venv/bin/python -m pytest cli/tests/test_cli.py

# All CLI tests
PYTHONPATH=. cli/.venv/bin/python -m pytest cli/tests/
```

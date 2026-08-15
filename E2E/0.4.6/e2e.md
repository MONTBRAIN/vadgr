# 0.4.6 - Rust engine: E2E runbook

> Status: implementation verification passes; the full live run is blocked by
> provider capacity. Results in this document come only from recorded commands.
> An operating system with no live session is `not run`, never pass from CI.

## Preconditions

- Use the implementation branch and an isolated Rust daemon port, database,
  configuration home, and `VADGR_RUNS_DIR`.
- Use the installed `vadgr-cua` executable through `VADGR_CUA_BIN`.
- Use the current native OAuth credential store. Never copy credentials into
  evidence.
- Start each independent pass from a new database and journal root.
- Drive the Rust daemon through HTTP, both WebSockets, and the unchanged Python
  CLI. Do not import the engine.

## Automated gates

| gate | result |
|---|---|
| unchanged Python engine, API and CLI suites | pass: 692 passed |
| Rust all-target suite | pass: 135 passed, 1 Docker-only test ignored |
| rustfmt | pass |
| clippy with warnings denied | pass |
| Linux musl release build | pass: x86-64 `static-pie linked` |
| installed artifact with empty environment | pass: complete health body returned |
| clean install in `scratch` | not run locally: Docker is not exposed to this WSL distribution; CI remains the gate |
| Windows compile branch | not run: this WSL host has no MinGW C compiler for bundled native dependencies |
| macOS compile branch | not run: this WSL host has no macOS C cross-compiler |

## Live seam

| field | result |
|---|---|
| host | WSL2 |
| provider | Anthropic OAuth, live Messages request |
| MCP transport | `rmcp` stdio to installed cua |
| requested tool | `computer-use__get_platform` |
| tool result | `wsl2` |
| input tokens | 11223 |
| output tokens | 36 |
| result | pass |

## Full surface

Three isolated WSL2 Rust daemons ran concurrently on ports `9461` to `9463`.
The installed Python CLI created and watched one run against each daemon. Its
launcher resolved to an older checkout at `694e4a3`, so this is diagnostic
failure-path evidence and not the required current-worktree CLI pass. All three
runs reached the direct Anthropic provider and failed with the same live `400`
response: the subscription was out of extra usage. One bounded Haiku check
returned the same account-wide response.

A fourth bounded diagnostic used the required current-worktree driver,
`PYTHONPATH=. python3 -m cli`, against the final static artifact. It reproduced
the same provider-capacity response and the same raw and mobile frame types.
This confirms the current CLI failure path, but it cannot replace a successful
model and cua round trip.

Each failed run recorded the same socket structure:

| stream | frame types |
|---|---|
| raw | `run_started`, `agent_started`, `agent_failed`, `run_failed` |
| mobile | `started`, `tool_call`, `failed`, `failed` |

The daemon started cua through rmcp, completed initialize plus `tools/list`,
then closed the child cleanly after the provider failure. The model returned no
response and no cua tool was dispatched, so these runs are failure-path
evidence, not E2E passes. Their journals correctly contain no model or tool
record.

The three successful live passes, structural comparison, bounded restart
proof, and owner dogfood batch remain blocked until provider usage is restored.
The implementation PR must not be merged or tagged on this evidence alone.

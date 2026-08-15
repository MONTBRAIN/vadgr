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
| clean install in `scratch` | pass in CI: static release binary installed alone, started, and returned the required health body |
| Windows native gate | pass in CI: build, test, clippy with warnings denied, and rustfmt |
| macOS native gate | pass in CI: build, test, clippy with warnings denied, and rustfmt |

The current CI run is
[`31889115490`](https://github.com/MONTBRAIN/vadgr/actions/runs/31889115490).
All ten jobs passed on implementation commit `4b7f7ed`, including the Ubuntu
native gate and the unchanged Python workflow jobs.

## Live seam

| field | result |
|---|---|
| host | WSL2 |
| provider | Anthropic OAuth, live Messages request |
| MCP transport | `rmcp` stdio to installed cua |
| requested tool | `computer-use__get_platform` |
| tool result | `wsl2` |
| input tokens | 11223 |
| output tokens | 46 |
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

A fresh retry on 2026-08-15 first passed the bounded live seam with
`computer-use__get_platform` returning `wsl2` and nonzero provider usage. The
three current-worktree CLI passes started immediately afterward with
`claude-opus-5`, but all three model requests received live HTTP 400 `out of
extra usage` before a model response.

Claude Code `2.1.229` then refreshed the same account credential and completed
a live Opus request. The three product passes still received the same HTTP 400.
A minimal direct Haiku request returned HTTP 200, so all three agents repeated
the required task with new databases and
`claude-haiku-4-5-20251001`. All three full vadgr requests again received the
same HTTP 400 before a model response.

The full request has an 8,192-token output budget, three system blocks and the
complete control and MCP tool catalog. The minimal request omits that body. The
evidence isolates the response to the full provider request before tool
execution, but it does not prove which body field controls the provider's
billing decision.

Each final Haiku run recorded the same raw socket structure:

| stream | frame types |
|---|---|
| raw | `run_started`, `agent_started`, `agent_failed`, `run_failed` |
| mobile, passes B and C | `started`, `tool_call`, `failed`, `failed` |
| mobile, pass A capture | `started`, `tool_call`, `failed` |

The daemon started cua through rmcp, completed initialize plus `tools/list`,
then closed the child cleanly after the provider failure. The model returned no
response and no cua tool was dispatched, so these runs are failure-path
evidence, not E2E passes. Their journals correctly contain no model or tool
record. The mobile stream maps `agent_started` to `tool_call` without an MCP
call. Passes B and C also map `agent_failed` and `run_failed` to two
indistinguishable `failed` frames.

The three successful live passes, structural comparison, bounded restart
proof, and owner dogfood batch remain blocked while Anthropic rejects the full
third-party request. The `0.4.7` provider correction does not retroactively
close this runbook. The implementation PR must not be merged or tagged on this
evidence alone.

# `rust/` - the daemon, being rewritten

The daemon is moving to Rust across `0.4.5` to `0.4.8`, by a strangler through
the API: this crate runs **beside** the Python daemon, on its own port and its
own database. The unchanged previous-release harness runs against Python. Its
non-engine cells also run against Rust in the split `0.4.5` runbook.

**`0.4.5` is the daemon minus the engine.** The process, configuration, the
SQLite layer, the gates, the transport adapter, and every surviving route that
needs none of the engine. **It cannot start or resume a run**: both need a loop
behind them, the loop arrives at `0.4.6`, and those two routes are absent rather
than stubbed.

Until the cutover at `0.4.8`, **the Python daemon is still the product.**

```bash
cargo build
cargo test

# against a copy of a real database, on its own port
VADGR_PORT=8156 VADGR_DB=/tmp/copy.db VADGR_TRANSPORT=tailscale \
  cargo run --release
```

| variable | default | what it selects |
|---|---|---|
| `VADGR_PORT` | `8100` | not `8000`: both daemons run at once |
| `VADGR_DB` | `data/vadgr-rust.db` | its own file, never the Python daemon's |
| `VADGR_TRANSPORT` | `loopback` | or `tailscale` |
| `VADGR_PROVIDERS` | `providers.yaml` | native providers; deprecated CLI rows are ignored |
| `VADGR_CONFIG_HOME` | platform config directory below | exact override for the directory containing daemon-owned `settings.json` |
| `VADGR_COMPUTER_USE` | `true` | the default when daemon settings have no cua toggle |
| `VADGR_CUA_BIN` | discovered | an explicit cua runtime path for transitional status |
| `VADGR_TAILSCALED_SOCKET` | native Unix socket below | the Linux, WSL or macOS tailscaled LocalAPI socket |
| `VADGR_TAILSCALED_PIPE` | the standard protected Tailscale pipe | the Windows tailscaled LocalAPI pipe |

| host | default vadgr config directory | default tailscaled endpoint |
|---|---|---|
| Linux and WSL | `$XDG_CONFIG_HOME/vadgr`, or `$HOME/.config/vadgr` | `/var/run/tailscale/tailscaled.sock` |
| macOS | `$HOME/Library/Application Support/vadgr` | `/var/run/tailscaled.socket` |
| Windows | `%APPDATA%\vadgr`, or `%USERPROFILE%\AppData\Roaming\vadgr` | `\\.\pipe\ProtectedPrefix\Administrators\Tailscale\tailscaled` |

Filesystem configuration stays in native `PathBuf` values, including values
that are not UTF-8. The daemon joins path components with the platform API,
creates missing database parents, and binds parsed IPv4 or IPv6 socket
addresses. Settings replacement preserves the previous file if a Windows
replacement fails.

Malformed settings, wrongly typed `computer_use` values and invalid
`VADGR_COMPUTER_USE` values are errors. The daemon does not replace or report
them as plausible defaults.

`PUT /api/settings/computer-use` writes only vadgr's `settings.json`. It does
not install a runtime and does not edit `.mcp.json`, Gemini settings or Codex
global settings. The native MCP host will read this toggle. The transitional
response keeps the fields the released CLI reads.

Runtime discovery checks `VADGR_CUA_BIN`, the platform-specific `.cu_venv`
console entry, then `PATH`. Windows follows `PATHEXT`; Unix requires an
executable file. Discovery does not start the runtime.

The Rust provider catalog includes only `kind: native` entries. It never starts
an external agent CLI to test availability.

**Copy a database with `VACUUM INTO`, never `cp`.** The daemon runs SQLite in
WAL mode, so a bare file copy is a different database: it carries what was last
checkpointed and drops everything still in the `-wal`. Copying one the obvious
way rolled a schema back past a whole release's migration, and the daemon then
answered `500 no such column` against what looked like a current file.

```bash
sqlite3 data/agent_forge.db "VACUUM INTO '/tmp/copy.db';"
```

## Layout

```
src/
├── main.rs        the process
├── config.rs      process settings and native providers
├── platform.rs    detected host and computer-use platform values
├── computer_use_setup.rs daemon-owned cua state and runtime discovery
├── error.rs       the error envelope, constructed in exactly one place
├── auth/          the gates, tokens, the pairing code
├── db/            the schema (copied verbatim) and the two repositories
├── transport/     tailscale over the local API socket, and loopback
├── routes/        the twelve HTTP routes this release serves
└── ws/            the fan-out, its replay buffer, and both sockets
tests/             envelope, pairing, repository, buffer, routes
```

The schema is **copied, not improved**. An improvement here would make every
evidence comparison in the migration meaningless, which is the constraint rather
than a preference.

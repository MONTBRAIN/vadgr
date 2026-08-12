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
| `VADGR_PROVIDERS` | `providers.yaml` | the provider catalogue |
| `AGENT_FORGE_COMPUTER_USE_ENABLED` | `true` | whether computer-use integration is enabled |
| `VADGR_COMPUTER_USE` | unset | compatibility alias for the computer-use flag |
| `VADGR_TAILSCALED_SOCKET` | `/var/run/tailscale/tailscaled.sock` | the tailscaled LocalAPI socket |

`PUT /api/settings/computer-use` performs the same setup or removal as the
Python daemon. It updates the supported agent configuration files and reports
the resulting state. The compatibility alias is only read when
`AGENT_FORGE_COMPUTER_USE_ENABLED` is not set.

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
├── config.rs      env, providers.yaml
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

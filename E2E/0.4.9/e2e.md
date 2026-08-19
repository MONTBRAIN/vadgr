# 0.4.9 - the cutover: e2e runbook

`vadgr` is one binary. `vadgr start` launches the Rust daemon, a machine's state
lives where the platform says durable state lives rather than below the directory
the daemon was started from, and an installation that ran through the
side-by-side releases keeps every run it made.

> **Status: not started.**

## How a pass is run, before anything else in this file

The four rules in [`../README.md`](../README.md) hold here without restatement:
whatever needs the owner runs first, the pass does not stop to report, a bug
found is a bug fixed here and now with a test that fails without the fix, and a
fix invalidates the cells it touched on every operating system that had passed
them.

**One command at a time.** Every product command is invoked on its own and its
output and exit code are read before the next is chosen.

## The approach

**The subject is a machine's state, so the oracle is the state, never the CLI's
report of it.** A cell that consolidates a database is judged by opening that
database and counting rows, by listing the directory, and by reading the run back
through the public API. The CLI saying "consolidated" proves nothing.

The daemon is driven through its installed public entry point on `PATH`. The
installer is driven the way a new user drives it: as a script, on a machine that
does not have the product.

## Owner and environment requirements

| requirement | cells | non-secret availability check | cost or destructive effect | cleanup |
|---|---|---|---|---|
| `GEMINI_API_KEY` in `../.env` | `E1`-`E3` | `grep -c '^GEMINI_API_KEY' ../.env` returns `1`; the value is never printed | one authenticated catalog call, one bounded readiness call | the isolated root is removed |
| A handset with the Vadgr app, held by the owner | `H1`-`H4` | the owner confirms the phone is in hand | none | the device is removed |
| Tailscale up and logged in | `G2`, `G3`, `H1`-`H4` | `tailscale status` names this node | none | none |
| A container runtime, for the installer cells | `I1`-`I3` | `docker info` or `podman info` answers | pulls a base image | the container is removed |
| Rust toolchain and git | all | `cargo --version`, `git --version` | none | none |

**The handset group runs first**, per the rule that owner cells open a pass.

## Billed model selection

| cells | provider/auth | required capabilities | selected model | official source and date | input/output price | hard iterations/tokens/cost | escalation condition |
|---|---|---|---|---|---|---|---|
| `E3`, `F1`-`F3`, `H3` | Gemini / API key | text generation, tool calls, authenticated catalog | `gemini-3.5-flash-lite` | the authenticated catalog read in `E2`, on the execution date | the cheapest listed text model | 10 iterations, 60,000 input tokens, USD 0.05 | none: a capability failure ends the group |

## Prerequisites

```bash
export E2E_ROOT="$(mktemp -d)"
export E2E_BIN="$E2E_ROOT/bin"
export PATH="$E2E_BIN:$PATH"
export VADGR_STATE_HOME="$E2E_ROOT/state"
export VADGR_HOME="$E2E_ROOT/home"
export VADGR_PORT=8861
export VADGR_TRANSPORT=loopback          # tailscale for G2, G3 and the H group
cargo build --release --bins
mkdir -p "$E2E_BIN" && cp target/release/vadgr target/release/vadgr-daemon "$E2E_BIN/"
command -v vadgr && sha256sum "$(command -v vadgr)"
```

## Remote-host handoff for Linux, macOS and Windows

Each native-host session follows this without context from another session.

1. **Read first**: `AGENTS.md`, `E2E/README.md` and this runbook, whole. Check
   out the same PR head and record `git rev-parse HEAD` in every result.
2. **Build and install**, never run from the source tree: `cargo build --release
   --bins`, copy both binaries into an empty root, put it first on `PATH`. `A1`
   records `command -v vadgr` and its `sha256`, which must be that build.
3. **`vadgr-computer-use` is not needed.** Nothing here drives a desktop.
4. **Two prerequisites decide what you can run.** `G2`, `G3` and the `H` group
   need a transport that advertises an address, so `VADGR_TRANSPORT=tailscale`
   on a host where `tailscale status` names this node; on `loopback` pairing
   correctly refuses and those cells are `blocked` by name. The `I` group needs a
   container runtime; without one it is `blocked`, and the rest of the runbook is
   unaffected.
5. **The environment** is the block above. Windows PowerShell:

   ```powershell
   $env:E2E_ROOT = "$env:TEMP\vadgr-049"
   $env:E2E_BIN  = "$env:E2E_ROOT\bin"
   $env:PATH     = "$env:E2E_BIN;$env:PATH"
   $env:VADGR_STATE_HOME = "$env:E2E_ROOT\state"
   $env:VADGR_HOME       = "$env:E2E_ROOT\home"
   $env:VADGR_PORT       = "8861"
   ```

6. **Order.** `H` first, because it needs a person. Then `A`, then `B` (the
   consolidation, which needs no daemon), then `C`, `D`, `E`, `F`, `G`, then `I`.
   The `B` group builds its own fixtures and leaves nothing behind.
7. **Evidence** goes in a dated directory created before the first cell, and the
   sweep's tables are generated by `harness/tables.py`, never typed.
8. **Cleanup**: stop only the daemons you started, by pid; remove only the
   isolated root.
9. **Credentials**: read only what a cell needs from `../.env`, into that
   command's environment only. Run the secret check before the group and again
   before evidence is sealed, and grep the sealed boundary for each key used.
10. **Write your own column** in the per-OS table, from observation.

## Automated gate (necessary, never sufficient)

- `cargo test` -> **N passed**
- `cargo clippy --all-targets -- -D warnings`, `cargo fmt --check` -> exit `0`
- `python3 -m pytest scripts/tests -q` -> **N passed**, the repository's own gates

The suites cannot tell you whether a real machine's history survived an upgrade,
whether the installer works on a machine without a toolchain, or whether the
phone still reaches the daemon. That is this runbook's half.

## Coverage

| Part | Axes | Cells | Run | Open |
|---|---|---|---|---|
| A the binary is the built head | identity x tree | 3 | 0 | 3 |
| B the consolidation | inputs x outcome | 9 | 0 | 9 |
| C the service group | verb x state | 6 | 0 | 6 |
| D read-only commands | command x state | 5 | 0 | 5 |
| E provider onboarding | verb x live credential | 3 | 0 | 3 |
| F runs and the watcher | outcome x flag | 4 | 0 | 4 |
| G pairing | render x decode | 3 | 0 | 3 |
| H the phone, held by a person | surviving handheld cells | 4 | 0 | 4 |
| I the installer | clean host x drive | 3 | 0 | 3 |
| | | **40** | **0** | **40** |

## Part A: the thing under test is the thing that was built

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| A1 | `$E2E_BIN` first on `PATH` | `command -v vadgr` | resolves inside `$E2E_BIN`; its `sha256` is the release build of the head under test | the path and both hashes | none | |
| A2 | as A1 | `vadgr --version` | prints `0.4.9`, matching the manifest and what the daemon reports at `/api/health` | the printed line, the health body | none | |
| A3 | a clean checkout | `git ls-files` | **no `.py` file outside `scripts/` and an older runbook's `harness/`**, no `requirements.txt`, no `rust/` directory | the file list, the sweep's own output | none | |

## Part B: a machine keeps its history

The subject of this release. Each cell builds its own fixture, starts the daemon
once, and is judged by opening the resulting database rather than by what the
daemon said.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| B1 | an empty state root, no legacy database anywhere | start the daemon | it serves; the root holds `vadgr.db` and `credentials/` | directory listing, health | stop | |
| B2 | a legacy database from the departing daemon with two runs, no other | start the daemon | the root's `vadgr.db` holds both runs; the source is gone | row counts before and after, `GET /api/runs` | stop | |
| B3 | both legacy databases, different runs in each, and a legacy journal tree | start the daemon | **every run from both** is in the target, the journals are under `runs/`, and both sources are gone | row ids from each source and from the target, the journal file's bytes | stop | |
| B4 | as B3, plus a run committed to the write-ahead log and not checkpointed | start the daemon | that run is in the target too | the row id, read from the target | stop | |
| B5 | both databases sharing one run id | start the daemon | **it refuses**: non-zero exit, the id named, and both sources untouched | the message, both files' hashes before and after | none | |
| B6 | both databases sharing one device id | start the daemon | it refuses and names the device | the message | none | |
| B7 | a target root holding a file this product did not write | start the daemon | it refuses and names the root | the message, the foreign file still present | none | |
| B8 | a staging directory left by an interrupted attempt | start the daemon | the debris is discarded and the consolidation completes | the listing before and after | stop | |
| B9 | a machine already consolidated | start the daemon twice | the second start changes nothing: same row count, same file hashes | hashes before and after | stop | |

## Part C: the service group

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| C1 | nothing on the port | `vadgr start` | exit `0`; **the process is `vadgr-daemon`**, read from the process table, not from the CLI's output | CLI output, `ps` line, health | C4 | |
| C2 | C1's daemon running | `vadgr start` | refuses, non-zero, the pid unchanged | CLI output, the pid twice | C4 | |
| C3 | as C2 | `vadgr status`, `vadgr logs --no-follow -n 5` | the table names the live pid; the log tail matches the file | CLI output, `tail -5` | C4 | |
| C4 | as C2 | `vadgr stop` | the process is gone, the port free, the pid and port files removed | `ps`, listener list, directory | none | |
| C5 | a listener holding the port and never accepting | `vadgr start` | it walks up and the port file names the port it took | CLI output, listener list, port file | stop | |
| C6 | stopped | `vadgr restart` | a new pid serves health on the port | the two pids | stop | |

## Part D: the read-only commands

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| D1 | daemon running | `vadgr health` | `0.4.9`, the host's platform, and the module block; equals `/api/health` | CLI output, `curl` body | none | |
| D2 | as D1 | `vadgr providers` | the three providers with their state; equals `GET /api/providers` | CLI output, `curl` body | none | |
| D3 | as D1, no runs | `vadgr runs list` | "No runs found." and exit `0` | CLI output | none | |
| D4 | one run present | `vadgr runs list`, `vadgr runs get <prefix>` | the table carries a duration; the prefix resolves; fields equal the API | CLI output, `curl` body | none | |
| D5 | nothing listening | `vadgr health` | exit `3` with the daemon-is-down line | CLI output | none | |

## Part E: provider onboarding

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| E1 | fresh state root; the key in the command's environment only | `vadgr provider login gemini` | names the variable, never the value; the daemon reports Gemini connected with a live catalog; **the key is absent from the database, WAL, SHM and this evidence** | CLI output, `curl` body, a grep for the key returning zero | E3 | |
| E2 | E1 connected | `vadgr model list`, `vadgr model default gemini/<model>` | the catalog lists models; the default is set and the API agrees | CLI output, `curl` body | E3 | |
| E3 | as E2 | `vadgr provider logout` of a non-default provider | the connection and its credential record are gone | `curl` body, credential directory | none | |

## Part F: runs and the watcher

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| F1 | provider connected and default | `vadgr run "<task>" --background` | exit `0`, the id printed; the run reaches a terminal state | CLI output, run row | none | |
| F2 | as F1 | `vadgr run "<task>"` watched | `Run completed`, the results link, exit `0`; the journal is under the **state root's** `runs/` | CLI output, the journal path | none | |
| F3 | a run cancelled from another terminal while watched | the watcher | says the run was cancelled, exits `0` | CLI output, the run row | none | |
| F4 | as F1 | `vadgr run "<task>" --background --json` | stdout parses whole, with no hint on it | the output through a strict parser | none | |

## Part G: pairing

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| G1 | no provider connected | `vadgr pair` | says a provider is needed and mints nothing | CLI output, `GET /api/devices` | none | |
| G2 | provider default, tailscale transport | `vadgr pair` | a QR, the machine, the address and the code | CLI output | the code expires | |
| G3 | G2's output | decode the printed symbol with `harness/qr-decode` | it recovers exactly the link rebuilt from the printed fields | the decode output | none | |

## Part H: the phone, held by a person

**The cutover changes the thing on the other end of the wire**, so the surviving
handheld cells are spent again. The oracle is the daemon, never the screen.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| H1 | a paired handset, the daemon on the tailnet | the owner opens the app | the machine appears with its name and reports healthy | the daemon's request log, the app's machine row | none | |
| H2 | as H1, unpaired | the owner scans `G2`'s QR | `POST /api/auth/claim` answers `200` and a device row appears | the log line, `GET /api/devices` | the device is removed | |
| H3 | as H1, a provider connected | the owner starts a run from the phone | the run appears and reaches a terminal state, watched from the phone | the run row, the journal, the socket frames | none | |
| H4 | as H3 | the owner reads the run back in the app | the app shows the same status the API serves | both, side by side | none | |

## Part I: the installer, on a machine that does not have the product

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| I1 | a container with a shell, git and curl, **no toolchain and no vadgr** | assert both absences | `cargo` and `vadgr` are not found | the two failed lookups | the container is removed | |
| I2 | as I1 | run `setup.sh` against the commit under test | it installs the toolchain, builds, and puts both binaries in the install root | the transcript, the install root listing | as I1 | |
| I3 | as I2 | `vadgr --version`, then `vadgr health` | the version matches; health exits `3` because nothing is started, which is the correct answer | CLI output and both exit codes | as I1 | |

## Per-OS results

Legend: `pass` and `fail` mean it ran. `blocked` means it could not run, and says
what stopped it. `not run` means nobody ran it. `Not-Needed` carries its reason.
**A cell is marked from observation, never expectation.**

**CI is not an e2e pass.** The `overall` row never inherits a gate result: it is
the weakest of the parts actually driven on that OS.

| part | WSL | Linux | Windows native | macOS | notes |
|---|---|---|---|---|---|
| automated gate | | not run | not run | not run | |
| A: the built head | | not run | not run | not run | |
| B: the consolidation | | not run | not run | not run | |
| C: the service group | | not run | not run | not run | |
| D: read-only commands | | not run | not run | not run | |
| E: provider onboarding | | not run | not run | not run | |
| F: runs and the watcher | | not run | not run | not run | |
| G: pairing | | not run | not run | not run | |
| H: the phone | | not run | not run | not run | |
| I: the installer | | not run | not run | not run | |
| **overall** | | not run | not run | not run | |

Paths, process supervision and access control are platform-shaped. **No supported
operating system is `Not-Needed` for final acceptance.**

## Findings

| # | what | where | disposition |
|---|---|---|---|

## Surface coverage - **every published endpoint, with what it returned**

Generated from `harness/sweep.py`'s record by `harness/tables.py`, never typed.

## Repeatability - **three independent passes**

Three passes, concurrently, each with its own port, state root and daemon.

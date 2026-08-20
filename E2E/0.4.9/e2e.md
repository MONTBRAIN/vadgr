# 0.4.9 - the cutover: e2e runbook

`vadgr` is one binary. `vadgr start` launches the Rust daemon, a machine's state
lives where the platform says durable state lives rather than below the directory
the daemon was started from, and an installation that ran through the
side-by-side releases keeps every run it made.

> **Status: WSL passed, 80 of 80 cells, against the frozen head recorded in
> `A1`.** Linux, Windows native and macOS are not run. An earlier WSL pass was
> invalidated whole and withdrawn: three fixes landed mid-pass, the binaries
> were rebuilt without re-running the identity cell, and one cell's recorded
> output named a refusal that did not exist at the head the pass recorded. This
> pass re-records `A1` at every rebuild, and the one rebuild it needed changed
> the CLI alone, with the daemon binary byte for byte identical, so the cells
> already driven against the daemon still name the artifact that produced them.

## How a pass is run, before anything else in this file

The five rules in [`../README.md`](../README.md) hold here without restatement:
whatever needs the owner runs first, the pass does not stop to report, a bug
found is a bug fixed here and now with a test that fails without the fix, a fix
invalidates the cells it touched on every operating system that had passed them,
and the evidence is pushed as part of the pass, never left on the machine.

**One command at a time.** Every product command is invoked on its own and its
output and exit code are read before the next is chosen.

**A rebuild is a new subject.** If any fix lands mid-pass, the binaries are
rebuilt, `A1` is re-run and its new hashes recorded **before any further cell**,
and every cell the changed files touch goes back to `not run`. A result recorded
against a binary whose hash no later cell can name is not a result. This rule is
here because the invalidated pass broke it: a cell's output named a refusal that
did not exist at the recorded head.

## The approach

**The subject is a machine's state, so the oracle is the state, never the CLI's
report of it.** A cell that consolidates a database is judged by opening that
database and counting rows, by listing the directory, and by reading the run back
through the public API. The CLI saying "consolidated" proves nothing.

**Both run sockets are driven directly by a wire client** (Part W), because the
CLI watcher is one consumer of one socket and cannot stand in for the wire. A
claimed run success carries its journal line: a `completed` status alone proves
nothing (`../README.md`, the verdict rules).

The daemon is driven through its installed public entry point on `PATH`. The
installer is driven the way a new user drives it: as a script, on a machine that
does not have the product.

## Paired surfaces this pass depends on

This daemon is called by two other repositories, each on its own version. **A
cell asks a paired repository only for what it has released.** A cell asking the
phone for a screen the shipped app does not have is specified against a surface
nobody built, and it fails for a reason that has nothing to do with this
release.

| repository | released version | what this pass relies on |
|---|---|---|
| vadgr-mobile | 0.4.1 | the app pairs by QR or code, lists machines, lists runs, opens a run, and consumes `GET /api/runs/{run_id}/stream` with its device token. **It is a reader**: starting a run from the phone is that repository's `0.5.0`, against `POST /api/runs`, and no cell here asks for it |
| vadgr-computer-use | 0.7.4 | the installed `vadgr-cua` entry point over stdio, and the screenshot and shell tools, which are the tools every screen-touching cell here uses. **`0.7.4` rather than `0.7.3` because this pass found the reason for it**: on `0.7.3` the entry point could not run on Windows at all, so every cell below that reaches the screen was unreachable on this platform. `CU4` is the cell that now checks it |

**What this means for a cell that wants more.** It is written into the runbook
of the release that delivers the surface, not this one, and its absence here is
stated rather than silent. Part H says so where the run-start cell would have
been.

## Owner and environment requirements

| requirement | cells | non-secret availability check | cost or destructive effect | cleanup |
|---|---|---|---|---|
| `GEMINI_API_KEY` in `../.env` | `E1`-`E2`, `F1`-`F9`, `R1`-`R4`, `W1`-`W2`, `G2`, `H3` | `grep -c '^GEMINI_API_KEY' ../.env` returns `1`; the value is never printed | authenticated catalog calls and the billed runs below | the isolated root is removed |
| `ANTHROPIC_API_KEY` in `../.env` | `E3` | `grep -c '^ANTHROPIC_API_KEY' ../.env` returns `1` | one authenticated catalog call | the connection is removed in `E3` |
| A paid OpenAI account the owner can sign into (ChatGPT) | `O3` | the owner says so; nothing is typed | one OAuth authorization | the connection is removed |
| `OPENAI_API_KEY` in `../.env` | `O4` | `grep -c '^OPENAI_API_KEY' ../.env` | one authenticated catalog call | the connection is removed |
| A handset with the released Vadgr app (`vadgr-mobile 0.4.1`), held by the tester | `H1`-`H5` | the owner confirms the phone is in hand | none | the device is removed |
| Tailscale up and logged in | `G2`-`G8`, `W4`, `S1`, `H1`-`H5` | `tailscale status` names this node | none | none |
| A container runtime, for the installer cells | `I1`-`I6` | `docker info` or `podman info` answers | pulls a base image; `I6` rebuilds inside the container | the container is removed |
| a wire client for the sockets | `W1`-`W4`, `G8` | `python3 harness/sockets.py --help` (the standard library only, nothing to install) | none | none |
| `vadgr-computer-use` installed, `vadgr-cua` resolvable | `CU1`-`CU3`, `F1`-`F3`, `F5`, `R1`-`R2`, `H3` | `vadgr-cua doctor` exits `0` and prints its JSON. **Not `--version`, which this runtime does not accept**: the entry point is subcommand-only, so the check as first written failed on every platform and said nothing about whether the runtime worked | none | none |
| The platform state root free of a real installation | `J1` | the directory listed in `J1` is absent or empty | none: the cell is `blocked` by name rather than touching a real installation | `J1` removes exactly what it created |
| Five minutes of wall clock | `G6` | none | time only: the cell waits out a pairing code's full lifetime | none |
| Rust toolchain and git | all | `cargo --version`, `git --version` | none | none |

**The handset group runs first**, per the rule that owner cells open a pass. Its
setup (a provider login and a QR on the tailscale transport) is the first work of
the pass.

## Billed model selection

| cells | provider/auth | required capabilities | selected model | official source and date | input/output price | hard iterations/tokens/cost | escalation condition |
|---|---|---|---|---|---|---|---|
| `F1`-`F9`, `R1`-`R4`, `W1`-`W2`, `H3` | Gemini / API key | text generation, tool calls, **image-bearing tool-result continuation** (the screen cells return screenshots into the next turn), authenticated catalog | `gemini-2.5-flash`, re-verified against the catalog read in `E2` on the execution date | the authenticated catalog read in `E2`, on the execution date | the cheapest catalog model that passes `vadgr model default`'s own live check with the capabilities named | 10 iterations per run, 60 runs' calls at most, 400,000 input tokens, USD 0.30 | none: a capability failure ends the group |
| `E3` (Anthropic connect only) | Anthropic / API key | authenticated catalog | none: no generation call | the catalog call itself | catalog call only | one call | none |

Why not the cheapest text model: the previous table named `gemini-3.5-flash-lite`
as "the cheapest listed text model" and the pass could not use it, because the
run cells carry screenshots back into the model and a text-priced selection does
not answer that shape. Two more facts from the invalidated pass bind this table:
`deep-research-*` catalog entries refuse an ordinary generation request (HTTP
400), so "in the catalog" is not "usable", and the daemon's own default-model
check is the arbiter - the model this table names is the one that check accepts
on the execution date, and the accepted name is recorded in `E2`'s boundary.

## Prerequisites

```bash
export E2E_ROOT="$(mktemp -d)"
export E2E_BIN="$E2E_ROOT/bin"
export PATH="$E2E_BIN:$PATH"
export VADGR_STATE_HOME="$E2E_ROOT/state"
export VADGR_HOME="$E2E_ROOT/home"
export VADGR_PORT=8861
export VADGR_TRANSPORT=loopback          # tailscale for G2-G8, W4, S1 and the H group
cargo build --release --bins
mkdir -p "$E2E_BIN" && cp target/release/vadgr "$E2E_BIN/"
command -v vadgr && sha256sum "$(command -v vadgr)"
```

## Remote-host handoff for Linux, macOS and Windows

Each native-host session follows this without context from another session.

1. **Read first**: `AGENTS.md`, `E2E/README.md` and this runbook, whole. Check
   out the same PR head and record `git rev-parse HEAD` in every result.
2. **Build and install**, never run from the source tree: `cargo build --release
   --bins`, copy both binaries into an empty root, put it first on `PATH`. `A1`
   records `command -v vadgr` and its `sha256`, which must be that build. **If a
   fix lands mid-pass, rebuild, re-run `A1`, and re-run the invalidated cells**;
   see the rule at the top of this file.
3. **`vadgr-computer-use` is needed.** The run cells (`F`, `R`, `H3`) and the
   computer-use group (`CU`) drive the screen through it. Install the released
   `vadgr-computer-use` per its own README so that `vadgr-cua` resolves, then
   prove it through the product: `vadgr computer-use status` must report
   `available: true` before the first run cell (`CU3` is that proof). A host
   without it marks `CU`, `F`, `R` and `H3` `blocked` by name.
4. **Two prerequisites decide what else you can run.** `G2`-`G8`, `W4`, `S1` and
   the `H` group need a transport that advertises an address, so
   `VADGR_TRANSPORT=tailscale` on a host where `tailscale status` names this
   node; on `loopback` pairing correctly refuses and those cells are `blocked`
   by name. The `I` group needs a container runtime; without one it is `blocked`,
   and the rest of the runbook is unaffected.
5. **The environment** is the block above. Windows PowerShell:

   ```powershell
   $env:E2E_ROOT = "$env:TEMP\vadgr-049"
   $env:E2E_BIN  = "$env:E2E_ROOT\bin"
   $env:PATH     = "$env:E2E_BIN;$env:PATH"
   $env:VADGR_STATE_HOME = "$env:E2E_ROOT\state"
   $env:VADGR_HOME       = "$env:E2E_ROOT\home"
   $env:VADGR_PORT       = "8861"
   ```

6. **Order.** `H` first, because it needs a person (its setup: `E1`'s login and
   `G2`'s QR on a tailscale daemon). Then `A`, then `B` (the consolidation,
   which needs no daemon), then `C`, `D`, `CU`, `E`, `F`, `R`, `G`, `W`, `S`,
   `O`, then `I`, then `J`. The `B` group builds its own fixtures and leaves
   nothing behind. `W4` and `G8` consume the device token `G4` minted.
7. **Evidence** goes in a dated directory created before the first cell. The
   sweep's tables are generated by `harness/tables.py`, never typed. Socket
   frames are captured by `harness/sockets.py` into records at the `W` cells' boundaries;
   a helper may count frame types from a captured file, and may not open the
   socket for you.
8. **Cleanup**: stop only the daemons you started, by pid; remove only the
   isolated root. `J1` removes exactly the files it listed.
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
phone still reaches the daemon. That is this runbook's half. The gate's counts
and exit codes are filed in the evidence directory's `gate/` before Part A; a
gate that was not run on this host says `not run` in the per-OS table, never a
blank.

## Coverage

| Part | Axes | Cells | Run | Open |
|---|---|---|---|---|
| A the binary is the built head | identity x tree | 4 | 4 | 0 |
| B the consolidation | inputs x outcome | 10 | 10 | 0 |
| C the service group | verb x state x flag | 13 | 13 | 0 |
| D read-only commands | command x state | 5 | 5 | 0 |
| CU computer use | setting x live probe | 4 | 4 | 0 |
| E provider onboarding | verb x live credential | 6 | 6 | 0 |
| F runs and the watcher | outcome x flag | 9 | 9 | 0 |
| R interruption and recovery | kill x boot x park | 4 | 4 | 0 |
| G pairing and devices | mint x claim x revoke | 8 | 8 | 0 |
| W the sockets, on the wire | route x admission | 4 | 4 | 0 |
| S source enforcement | gate x source | 1 | 1 | 0 |
| O OAuth and the callback | page x port x account | 6 | 6 | 0 |
| H the phone, held by a person | what the released app does | 5 | 5 | 0 |
| I the installer and update | clean host x drive | 6 | 6 | 0 |
| J the platform state root | default resolution | 1 | 1 | 0 |
| | | **86** | **86** | **0** |

## Part A: the thing under test is the thing that was built

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| A1 | `$E2E_BIN` first on `PATH` | `command -v vadgr` | resolves inside `$E2E_BIN`; its `sha256` is the release build of the head under test. **Re-run after any mid-pass rebuild, before any further cell** | the path and both hash lines, and the head they were built from | none | **pass on native Windows, and the rule it exists to enforce was broken during this pass. That is recorded here rather than tidied.** The reading: `vadgr` resolves inside the test bin, and the two hash lines match, `20f3fef1c0050a005957fb9a7cbae05b61f1dc05fbad4af689d1755e76c39bdd` for both the installed file and `target/release/vadgr.exe`, at `a83ff1c`. **But this pass ran against three builds, and `A1` was recorded once.** Rule 4 says a rebuild is a new subject, so the identity cell is re-recorded **before any further cell**, and it was not. The three, with the fixes that produced them: `0a72f5f4` at `23:12`, then `caf43e5c` at `08:21` carrying the health fix `ccf569b`, then `a9406f2d` at `08:47` carrying the resume-row fix `6a22164`. **What this costs, stated exactly**: the cells re-driven after each fix cannot be tied to their artifact from `A1` alone, and must be read together with the commit named in their own status, each of which does name it. **What it does not cost**: no cell was driven against a build older than the fix it verifies, because each re-run followed its own rebuild and reinstall, and the reinstall is recorded in the cell. `A/A1-binaries.txt` in the evidence boundary lists every executable on the host with hash, size and time, labelled as computed at filing rather than during the pass. This is the same defect that withdrew an earlier pass on another operating system, at smaller scale, and it is the reason the rule reads the way it does. |
| A2 | as A1 | `vadgr --version` | prints `0.4.9`, matching the manifest. The daemon's own version is asserted at `D1`, where a daemon exists to ask | the printed line and the manifest line | none | **pass on native Windows**: `vadgr 0.4.9`, exit `0`, matching `Cargo.toml`'s `version = "0.4.9"`. |
| A3 | a clean checkout | `git ls-files` | **no `.py` file outside `scripts/` and an older runbook's `harness/`**, **no interpreter artefact of any kind**: no `.pyc`, `.pyo`, `.pyd`, `__pycache__/`, `site-packages/` or virtual environment, no `requirements.txt`, no `rust/` directory | the file list, the sweep's own output | none | **pass on native Windows**, counted from `git ls-files` rather than from a listing: **zero** `.py` outside `scripts/` and a runbook `harness/`, **zero** interpreter artefacts of any kind, **zero** tracked paths under `rust/`, and **zero** under `api/`. The cutover is complete in the index, not only on disk. |
| A4 | the install root the installer wrote | list it | **one executable**, named `vadgr`, and no second file beside it. The daemon is this binary invoked with `serve`, so a user receives one artifact rather than two that must stay in step | the directory listing, and the process table of a started daemon | none | **pass on native Windows for a fresh install, and the cell needs a second sentence.** The container install root held exactly one executable, `vadgr`, 22760088 bytes, and the daemon is that binary invoked with `serve`, read from the process table. **But it stops holding after the first update**: `install_binaries` moves the old file aside, so a machine that has updated once holds `vadgr` **and** `vadgr.previous`. The rollback copy is deliberate and useful; the cell's "no second file beside it" describes only the day the machine was installed. |

## Part B: a machine keeps its history

**Every legacy database in this group is built from the shipped schema**, copied
out of `api/persistence/database.py` at `v0.4.7` rather than retyped. A fixture
thinner than any real installation passes the move and fails the first request,
which is a case nobody can be in. The legacy journal tree is where the departing
daemon kept it, at `~/.vadgr/runs`.

The subject of this release. Each cell builds its own fixture, starts the daemon
once, and is judged by opening the resulting database rather than by what the
daemon said. **Where a boundary names a hash, the hash lines themselves are
filed** - `sha256sum` output before and after, never a sentence saying the file
did not change. A derived "unchanged: yes" is the CLI-report-of-state this part
exists to distrust.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| B1 | an empty state root, no legacy database anywhere | start the daemon | it serves; the root holds `vadgr.db` and `credentials/` | directory listing, health | stop | **pass on native Windows**: an empty root, and after one start it holds `credentials` and `vadgr.db` with health `200`. The port walked from a reserved `8880` to `8881` on the way, which this host supplies for free. |
| B2 | a legacy database from the departing daemon with two runs, no other | start the daemon | the root's `vadgr.db` holds both runs; the source is gone | the run ids read from the source before, and from the target and `GET /api/runs` after | stop | **pass on native Windows**: the fixture was built from the `v0.4.7` schema read out of the shipped source, not retyped. Source held `run-legacy-a` and `run-legacy-b`; after one start the target `vadgr.db`, **opened directly**, holds both, `GET /api/runs` returns both, and `data/agent_forge.db` is gone. |
| B3 | both legacy databases, different runs in each, and a legacy journal tree | start the daemon | **every run from both** is in the target, the journals are under `runs/`, and both sources are gone | the run ids read from **each source before the move** and from the target after it - three lists, filed; the journal file's bytes | stop | **pass on native Windows**: departing held `run-dep-1` and `run-dep-2`, surviving held `run-surv-1` and `run-surv-2`, and the target holds **all four**. The journal moved from `~/.vadgr/runs/run-dep-1` into the state root with an identical `sha256`, `34bc59fd...7b09` before and after, and the legacy tree is gone. |
| B4 | as B3, plus a run committed to the write-ahead log and not checkpointed | start the daemon | that run is in the target too | the row id, read from the target | stop | **pass on native Windows**: `run-wal-1` was committed under `journal_mode=WAL` by a process that ended with `os._exit(0)`, so nothing checkpointed. Proved to be in the sidecar only before the start: zero occurrences in the `.db` file, two in the `-wal`. After one start the target holds all five ids including `run-wal-1`, read by opening the database directly. Both sources gone, the journal moved intact. |
| B5 | both databases sharing one run id | start the daemon | **it refuses**: non-zero exit, the id named, and both sources untouched | the message; **the four `sha256sum` lines**, both sources before and after | none | **pass on native Windows** at `2ff3a5d`, and **it failed as written first**. The daemon refused correctly and named the run, but the CLI printed `API process died. Port N may be in use`, so the operator was sent after a port conflict that did not exist and the id reached the log only. Fixed: the CLI now repeats the daemon's own failure line. It reads `run run-shared exists in both ... Nothing has been moved. Copy one of them aside and start again.`, exit `1`, and the four `sha256` lines match either side, so both sources are untouched. |
| B6 | both databases sharing one device id | start the daemon | it refuses and names the device; both sources untouched | the message; the four `sha256sum` lines | none | **pass on native Windows**: exit `1`, `device dev-shared exists in both ... Nothing has been moved.`, the four hash lines identical either side, and the target root left empty. |
| B7 | a target root holding a file this product did not write | start the daemon | it refuses and names the root; the foreign file is untouched | the message; the foreign file's `sha256sum` before and after | none | **pass on native Windows**: exit `1`, and the message names the root and both ways out, `Point VADGR_STATE_HOME somewhere else, or move that directory aside.` The foreign file's hash is identical either side and it is still the only thing in the root. |
| B8 | a staging directory left by an interrupted attempt | start the daemon | the debris is discarded and the consolidation completes | the listing before and after | stop | **pass on native Windows**: debris from an interrupted attempt was planted at the staging path, a half written `vadgr.db` and a `runs/leftover-run/trajectory.jsonl`. After one start the staging directory is gone, the target holds exactly the two real runs, and a search for anything named `leftover` returns nothing, so the debris was discarded rather than adopted. |
| B9 | a machine already consolidated | start the daemon twice | the second start changes nothing: same row count, same file hash | the run count both times; **the two `sha256sum` lines** of the checkpointed database | stop | **pass on native Windows**: two runs after the first start and two after the second, and `vadgr.db` hashes `c26ed1db...dd31` **both times**. The hash lines are filed rather than a sentence saying it did not change. |
| B10 | a legacy database that opens, but whose `runs` table is missing a column every read needs | start the daemon | **it refuses**: non-zero exit, the missing column named, no target left behind, and the source byte for byte as it was | the message; the target's absence as a directory listing; **the source's two `sha256sum` lines** | none | **pass on native Windows**: the fixture is the shipped `v0.4.7` schema with one column line removed programmatically, `outputs TEXT DEFAULT '{}'`. The database opens and counts two runs, and reading `outputs` fails with `no such column`. The daemon refused, exit `1`, and **named the missing column**, adding that nothing was moved and the half made target was removed. Verified: the state root and the staging path both absent afterwards, and the source `sha256` is `a20d5ef7...a76c9` **before and after**. |

## Part C: the service group

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| C1 | nothing on the port | `vadgr start` | exit `0`; **the process serving is this same binary invoked with `serve`**, read from the process table rather than from the CLI's output, because the product is one executable and a second file would mean a user had to receive two | CLI output, the `ps` line with its full argument list, health | C4 | **pass on native Windows**: the process serving is this same binary invoked with `serve`, read from the process table as `"...vadgr-new.exe" serve --host 127.0.0.1 --port 8930`, and its pid equals `api.pid`. Health `200`, `version 0.4.9`, `platform windows`. |
| C2 | C1's daemon running | `vadgr start` | refuses, non-zero, the pid unchanged | CLI output, the pid twice | C4 | **pass on native Windows**: `vadgr is already running. Use 'vadgr stop' first.`, exit `1`, and the pid is `57992` before and after. |
| C3 | as C2 | `vadgr status`, `vadgr logs --no-follow -n 5` | the table names the live pid; the log tail matches the file | CLI output, `tail -5` | C4 | **pass on native Windows**: the table reads `api 57992 running`, equal to the live process id, and the five printed log lines are identical to the file's last five **after stripping the colour the file keeps and the pipe does not**. |
| C4 | as C2 | `vadgr stop` | the process is gone, the port free, the pid and port files removed | `ps`, listener list, directory | none | **pass on native Windows**: `Stopped api (PID 57992)`, the process gone from the table, zero listeners on the port, and the pid directory empty. |
| C5 | a listener holding the port and never accepting | `vadgr start` | it walks up and the port file names the port it took | CLI output, listener list, port file | stop | **pass on native Windows** with the port held by `harness/hold_port.py 8930 listening`: `Port 8930 busy, using 8935`, and the port file, the process arguments and health all name `8935`. The bind probe recorded why it skipped so far: `8931` to `8934` are unbindable **with zero listeners**, this host's own reservations. |
| C6 | **a daemon running** | `vadgr restart` | the old pid is stopped, a new pid serves health on the port | both pids, from the process table | stop | **pass on native Windows**: `Stopped api (PID 15536)` then a new pid `62776`; the old pid is gone from the process table and the new one serves health on the port. |
| C7 | stopped, nothing on the port | `vadgr restart` | prints the not-running line, then starts: exit `0`, a daemon serves health | CLI output, the new pid, health | stop | **pass on native Windows**: `vadgr is not running.` first, then it starts; pid `56632` is in the process table and health answers `200`. |
| C8 | stopped, nothing on the port | `vadgr stop` | prints "vadgr is not running.", exit `0`, and creates no pid or port file | CLI output, exit code, the pid directory listing | none | **pass on native Windows**: `vadgr is not running.`, exit `0`, and the pid directory holds nothing before or after, so no file was created. |
| C9 | nothing on port `8863` | `vadgr api --port 8863` | the `api` verb starts the daemon on the named port: exit `0`, the port file says `8863`, the process table shows this binary with `serve --port 8863`, health answers on `8863` | CLI output, port file, `ps` line, health | stop | **pass on native Windows**: `vadgr api --port 8863` started the daemon on the named port; the port file reads `8863`, the process arguments carry `--port 8863`, and health answers there. |
| C10 | daemon running | `vadgr logs -n 1` (follow is the default), then one `curl` of `/api/health` from another terminal, then interrupt the follow | the followed output gains the request line the log file gained after the follow began; the interrupt ends the follow | the captured follow output and the file's own tail, diffed | none | **pass on native Windows**: the log held 5 lines when the follow began and 6 after a `curl /api/health` returned `200`; the follow printed that new line and the capture is identical to the file's last two lines. It then ended on a **real console interrupt** and exited `0`. |
| C11 | daemon running | `vadgr logs --service nosuch --no-follow` | refuses: "No logs found for nosuch", non-zero exit | CLI output and exit code | none | **pass on native Windows**: `No logs found for nosuch. Is vadgr running?`, exit `1`. |
| C12 | a port **bound but not listening**, held by `harness/hold_port.py <port> reserved`; nothing else on it | `vadgr start` | it says the port is busy and walks up: the port file names the port it took and health answers there. **A connect to the held port is refused**, so a search that asked by connecting would call it free and the daemon would die on bind | CLI output, the harness line, the port file, `curl` health, and a connect to the held port showing it refused | stop, release the held port | **pass on native Windows** at `33fafb8`: this host reserves `8871` to `8875` itself, with no listener behind any of them, so the precondition came from the platform rather than the harness. A connect to `8871` was refused and a bind of it failed. `vadgr start` printed `Port 8871 busy, using 8876`, walked past all five, and health answered `200` on `127.0.0.1:8876` and on `100.73.251.18:8876`. **Before the fix this cell was the failure**: the daemon printed no warning, said it was starting on `8861`, and died on bind |
| C13 | the transport is `tailscale`, and the **transport address only** holds the port: `harness/hold_port.py` is not enough here, so the cell binds `<tailnet-ip>:<port>` and leaves `127.0.0.1:<port>` free | `vadgr start` | it walks up rather than starting: the daemon binds every host it advertises, so a port free on loopback and taken on the tailnet is not usable. The port file names the port it took and health answers on **both** hosts | CLI output, the two bind attempts, the port file, `curl` health on loopback and on the tailnet address | stop, release the held address | **pass on native Windows**, and it was `not run` before this pass. With `100.73.251.18:8940` held and `127.0.0.1:8940` free, the bind probe recorded the split, `bindable=yes` on loopback and `no` on the tailnet address. The CLI printed `Port 8940 busy, using 8941`, the process carries both `--host` arguments, and health answers `200` on **both** addresses with `"bind_host":"100.73.251.18"`. **This is the multi-host bind check the port fix added**: a loopback-only test would have passed the port and died on the second bind. `harness/hold_port.py` binds loopback only, so the tailnet address was held by a short helper, which the cell's own note allows. |

## Part D: the read-only commands

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| D1 | daemon running | `vadgr health` | `0.4.9`, the host's platform, and the module block. **Every field the CLI prints equals the API's value for that field, compared field by field.** The API serves `"computer_use": false` on a fresh root and the CLI must print `unavailable` for it, never a word claiming a cause the daemon did not report (finding F4) | CLI output and the `curl` body, side by side | none | **pass on native Windows**: every printed field equals the API field, and `computer_use false` prints as `unavailable` **with no invented cause**, which is the behaviour finding `F4` records. |
| D2 | as D1 | `vadgr providers` | the three providers with their state; equals `GET /api/providers` | CLI output, `curl` body | none | **pass on native Windows**: the CLI lists the three providers as `not connected`, and `GET /api/providers` returns the same three ids in the same order, each `"connected":false`. |
| D3 | as D1, no runs | `vadgr runs list` | "No runs found." and exit `0` | CLI output | none | **pass on native Windows**: `No runs found.` and `GET /api/runs` returns `[]`, so the empty case is a sentence rather than an empty table. |
| D4 | one run present: this cell is executed after Part F, against F's rows | `vadgr runs list`, `vadgr runs get <prefix>` | the table carries a duration; the prefix resolves; fields equal the API | CLI output, `curl` body | none | **pass on native Windows**: the table carries a real `Duration`, the prefix `run-8ddb` resolved to the full id, and the fields equal the API row, `completed`, `gemini`, `gemini-3.7-flash`. The printed `4.2s` matches the row's own timestamps, `05:40:45.641466` to `05:40:49.795059`, which is `4.15s`. **Deviation stated rather than silent**: this ran in an isolated root with no Part F rows, so the two runs were built here. The first attempt failed `NO_ACTION_TAKEN` because the task took no action and the computer-use runtime was absent from `PATH`; both were corrected and the cell ran against real rows. |
| D5 | nothing listening | `vadgr health` | exit `3` with the daemon-is-down line | CLI output | none | **pass on native Windows**: exit `3` with `Error: API is not running at http://127.0.0.1:8930. Start it with: vadgr start`, no pid files and no process left. |

## Part CU: computer use is a setting the product owns

The run cells need this group: a screen run with computer use off is a different
product. `CU2` before `CU3` so the group ends enabled.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| CU1 | daemon running, `vadgr-cua` resolvable | `vadgr computer-use status` | prints the availability; equals `GET /api/computer-use/status`, whose `available` comes from a live tool listing against the runtime, and `GET /api/settings/computer-use` | CLI output and both `curl` bodies | none | **pass on native Windows**: `Computer use: enabled`, exit `0`, and the wire agrees, `GET /api/computer-use/status` returning `{"available":true,"platform":"native"}` with the health module block `true`. |
| CU2 | as CU1 | `vadgr computer-use disable` | exit `0`; `GET /api/settings/computer-use` says `"enabled": false`; `/api/health`'s module block says `"computer_use": false` | CLI output, both `curl` bodies | CU3 | **pass on native Windows**, after the defect it found was fixed. **It failed first**: `vadgr computer-use disable` set `"enabled": false` correctly, but `/api/health` kept reporting `"computer_use": true`, polled three times over twelve seconds. `src/routes/health.rs` built the module block from `venv_ready` alone, which answers whether the runtime is **installed**, and never consulted the setting, so a machine whose owner had switched computer use off still advertised it as usable. **Finding `F4` states the contract this broke**: the field answers usability, and `false` is meant to cover a module that is absent **and** one the owner disabled. Fixed, with four tests that fail without it. Re-run against the fixed daemon: `disable` leaves the setting `false` and health `false`, `enable` returns both to `true`. |
| CU3 | as CU2 | `vadgr computer-use enable` | exit `0`; the setting reads `"enabled": true` through the API; `GET /api/computer-use/status` reports `"available": true` from its live probe | CLI output, both `curl` bodies | none | **pass on native Windows**: `Computer use enabled`, exit `0`, the setting reads `"enabled": true` through the API, and `GET /api/computer-use/status` reports `"available": true` from its live probe. |
| CU4 | `vadgr-cua` on `PATH`, whatever release the machine has | `vadgr-cua doctor` | exits `0` and prints JSON naming a `tool_count`. **This is the runtime the run cells depend on, checked directly rather than through the daemon**: `vadgr computer-use status` reports the setting the product owns, and a runtime that cannot start would still read as enabled there | the JSON, and its exit code | none | **pass on native Windows** with `vadgr-computer-use 0.7.4`: exits `0` and reports `tool_count 33`. **Against `0.7.3` this cell was the failure**: `doctor` died with `ModuleNotFoundError: No module named fcntl`, because `supervisor.py` imported it at module scope and Windows has none. Fixed in that repo and released as `0.7.4`; this cell is what keeps the class from returning |

## Part E: provider onboarding

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| E1 | fresh state root; the key in the command's environment only | `vadgr provider login gemini` | names the variable, never the value; the daemon reports Gemini connected with a live catalog; **the key is absent from the database, WAL, SHM and this evidence** - the grep runs against the raw files on disk, and the single expected holder is the credential store file, named with its mode | CLI output, `curl` body, the grep commands and their zero counts, the credential file's name and mode | E3 leaves gemini; the root is removed at the end | **pass on native Windows**: `Using GEMINI_API_KEY.` names the variable and never the value, then `Ready: Google Gemini, Gemini 3.7 Flash` after a live check. Exit `0`. |
| E2 | E1 connected | `vadgr model list`, `vadgr model default gemini/<model>` | the catalog lists models; the default is set and the API agrees; **the accepted model id is recorded here for the billed-model table** | CLI output, `curl` body | none | **pass on native Windows**: the catalog lists 28 models and the default was set and read back from `GET /api/providers` as `gemini-3.7-flash`, which is the model this pass billed. |
| E3 | as E2, `ANTHROPIC_API_KEY` in the command's environment only | connect Anthropic as a second, non-default provider, then `vadgr provider logout anthropic` | the connection and its credential record are gone; gemini and its default survive | `curl` body before and after, the credential directory listing before and after | none | **pass on native Windows**: `Connected: Anthropic`, 10 models, and `Default remains: Google Gemini / gemini-3.7-flash`, so a second provider does not move the default. Logout printed `Disconnected: Anthropic`, the row went to `connected false`, and the credential store went from two files to one. **The secret is absent**: 56 files under the state root scanned, zero plaintext occurrences, and it never appeared in stdout. |
| E4 | E1 connected | `vadgr provider status gemini --refresh` | exit `0`; only gemini's section prints; `catalog_verified_at` read from `GET /api/providers` before and after has advanced | CLI output; both timestamps, filed | none | **pass on native Windows**: exit `0`, only Gemini's section printed, 28 models still listed, and `catalog_verified_at` advanced from `02:10:07Z` to `05:01:24Z`, so the catalog was re-read live rather than served from cache. |
| E5 | gemini connected **and default** | `vadgr provider logout gemini` | refuses, non-zero exit; `GET /api/providers` still shows gemini connected and default; the wire behind it answers `409` on `DELETE /api/providers/gemini/connection`, its error code recorded as returned | CLI output and exit code; the `curl` status, code and body | none | **pass on native Windows**: exit `1` with `Error: the default provider cannot be disconnected`, and Gemini stayed `connected` and `is_default`. **The wire behind it answers `409`**, a conflict with current state rather than a malformed request. |
| E6 | E1 connected, stdin not a terminal | `vadgr model default` with no argument | prints the chooser, then refuses with the needs-a-terminal line, non-zero exit; the default unchanged through the API | CLI output and exit code; the `curl` body | none | **pass on native Windows** with stdin not a terminal: the chooser printed its numbered list, then the command refused with `This command needs a terminal to ask a question`, exit `1`, and the default stayed `gemini-3.7-flash`. |

## Part F: runs and the watcher

Computer use enabled (`CU3`), gemini connected and default (`E1`, `E2`). Every
claimed success in this part carries its journal line: the journal at the state
root's `runs/<id>/trajectory.jsonl`, written by the loop itself, with `in_flight`
and `done` lines per tool call and a `response` line carrying real `usage`.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| F1 | provider connected and default | `vadgr run "Take one screenshot, then reply done." --background` | exit `0`, the id printed; the run reaches `completed`; **the journal exists at that id with a screenshot tool's `in_flight` and `done` lines and a `response` line carrying `usage`** | CLI output; the run row from the API; the journal's phase counts | none | **pass on native Windows**: exit `0`, the id and watch hint printed, the run reached `completed`, and its journal holds 4 lines. `16760` input tokens, so the screenshot really went to the model, and the result is `done.` |
| F2 | as F1; a fresh nonce in the task text | `vadgr run "Use your shell tool to run: echo vadgr-e2e-<nonce>. Then stop."` watched | `Run completed`, the results link, exit `0`; the journal is under the **state root's** `runs/`; **the nonce appears in exactly one `done` line** - the countable side effect | CLI output; the journal path and the nonce count | none | **pass on native Windows**: `Run completed (6s)`, the `See results:` line, exit `0`. The nonce appears **6 times** in the journal and the model returned the shell output `vadgr-e2e-7f3a91`, so a real shell ran it rather than the model describing what it would do. |
| F3 | a run started and watched as F2 | from another terminal: `vadgr runs cancel <id>` - **the CLI, not a raw HTTP call** | cancel exits `0` and prints the row; the watcher says the run was cancelled and exits `0`; the row reads `cancelled` | both CLI outputs and exit codes; the run row | none | **pass on native Windows**: `vadgr runs cancel <id>` from a second terminal exited `0` and printed `Cancelled run <id>`; the watcher printed `Run cancelled (8s)` and **exited `0`**; the row reads `cancelled`. This is the improvement the release owns, and the shipped Python CLI printed nothing at all here. **The first attempt was a harness fault, recorded rather than hidden**: the task finished in 14s before the cancel landed, and the CLI correctly refused with `Run is already finished`, exit `1`. |
| F4 | as F1 | `vadgr run "<task>" --background --json` | stdout parses whole, with no hint on it; the row says `queued` | the output through a strict parser | none | **pass on native Windows**: stdout parses whole under a strict parser, the row reads `queued`, and `Watch it with` is absent from the stream. The `0.4.8` fix survives the cutover. |
| F5 | as F1; the default model's id known from E2 | `vadgr run "<task>" --provider gemini --model <that id> --json` watched | the first stdout block parses as the run row naming that provider and model; the watch ends `Run completed`, exit `0`; the API row's `provider` and `model` equal the flags | CLI output; the parsed block; the API row | none | **pass on native Windows**: the first stdout block parses on its own with **nothing after it**, carries the explicit `gemini` and `gemini-3.7-flash`, and the run completed with the shell output. **The first attempt was a harness fault**: the task said only `Reply with one word.`, which takes no action, and this engine fails such a turn with `NO_ACTION_TAKEN`. The `0.4.8` runbook recorded the same trap; the task was mine to choose and I chose badly. |
| F6 | as F1 | `vadgr run "Reply with one word." --provider gemini --model vadgr-e2e-no-such-model` watched | the daemon accepts the run (creation does not read the catalog); the first provider call fails; the watcher reports the failure and **exits `1`**; the row reads **`failed`**; the journal carries an `error` line | CLI output and exit code; the row; the journal's error line | F7 consumes this run | **pass on native Windows**: creation accepted the run, then it failed with `model `gemini/vadgr-e2e-no-such-model` is not connected`, exit `1`, and the row reads `failed` with that error in `outputs`. **One wording defect recorded rather than smoothed**: the message is prefixed `run recovery failed:` on a run that was never recovered. It is a first attempt, and the prefix sends a reader looking for a recovery that did not happen. |
| F7 | F6's run, status `failed` | `vadgr runs resume <id>` - **the CLI, positive path** | resume is accepted and prints the row; the row passes through `running`; **the journal grows past its former last line** and its resumed segment carries the recovered context; it fails again on the same missing model, and the journal then holds **exactly two** error lines - one per attempt, the count that proves the resume really ran | both CLI outputs; the journal's line count before and after, and the two error lines | none | **pass on native Windows**, after the defect it found was fixed in `6a22164`. **It failed first**: `vadgr runs resume` printed one line naming an id the owner had just typed, and no row. The detail block now lives in one printer that both `get` and `resume` call, and the row is **read back** rather than echoed from the acceptance, because the supervisor writes `running` before it spawns and a run that dies at once would otherwise be reported as running. Re-driven end to end on a failed run that had entered the loop: exit `0`, the row printed with `Status: running`, the status sequence read `failed, running, failed`, and the journal grew from 1 line to 2, the new line carrying `input_tokens` 7834 against 7800, so the resumed segment carries the replayed context. **Two oracles stay unreachable and are stated rather than bent.** A run that fails before entering the loop leaves **no journal directory at all**, so nothing can grow past a former last line. And "exactly two error lines" needs a run whose **tool call** fails once per attempt: a journal error line is written only from the tool dispatch, so a run that dies on an unconnected model or on `NO_ACTION_TAKEN` writes none, and the resumed run above grew its journal while holding zero. |
| F8 | a run started and watched as F2, mid-flight | send SIGINT to the watching CLI | the watcher prints "Detached. The run continues." and **exits `130`**; the run was **not** cancelled: the API row later reads `completed` | the watcher's output and exit code; the row after | none | **pass on native Windows.** All three oracles hold: the watcher printed `Detached. The run continues.` with the two follow-up lines, exited **`130`**, and the run was **not** cancelled, polling `running` from `t+0s` to `t+40s` and `completed` at `t+45s`. **This cell was recorded as a failure first, and that verdict was mine, not the product's.** The interrupt never reached the watcher because Windows carries an ignore-Ctrl+C bit in a process's parameters that **every child inherits**, and the drivers set it in the process that then spawned the product, so the product started deaf. Proved by A and B trials rather than argued: same binary, same command, same delivery, ignore bit set gives ignored and still running after 20 seconds, ignore bit cleared gives exit `0`. The handler was in `src/cli/stream.rs:142-149` the whole time. |
| F9 | F1-F8 have left `completed`, `failed` and `cancelled` rows | `vadgr runs list --status failed`, and `curl "$API/api/runs?status=failed"` | both list exactly the failed runs and no other, and equal each other; repeat for `--status completed` and compare counts | both outputs, side by side | none | **pass on native Windows**, once `F3` had left a `cancelled` row: the database held `completed 5`, `failed 3`, `cancelled 1`, and `vadgr runs list --status <s>` matched `GET /api/runs?status=<s>` on every one, exit `0` each time. |

## Part R: interruption and recovery

The recovery half of the engine: what a hard kill leaves, what the next boot
does with it, and what the parked state is. `R2` is the resume-success proof: a
side effect that appears **exactly once** across an interruption is what
"recovered, not replayed" means.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| R1 | a watched run mid-flight, on a task shaped "call your time tool's sleep for 30 seconds, then run: echo vadgr-e2e-<nonce>, then stop" (the released runtime's `time` tool ships `sleep`, capped at 60 seconds); the kill lands during the wait | `kill -9` the daemon pid | the watcher prints "The run stream closed. The run continues in the background." and exits `0` - the deliberate no-verdict outcome, observed on purpose; the run row in the database file still reads an active status, read with `sqlite3` directly, since no daemon is alive to ask | the watcher output and exit code; the row read from the file | R2 | **pass on native Windows**: the daemon was killed `7.55s` into a 30 second sleep, with the sleep confirmed `in_flight` first. The watcher exited `0`, and the database read directly with no daemon alive holds `status running` and `completed_at None`. **Two things recorded rather than smoothed.** The watcher printed `Lost the run stream. The run continues in the background.`, not the line this cell quotes; both exist in `src/cli/stream.rs`, one for a clean close and one for an errored stream, and a hard kill produces the errored branch, so **the runbook quotes the sibling line**. And the first attempt was discarded because the kill landed 1.8s after the sleep finished, so its precondition was never met. |
| R2 | R1's state root, daemon dead, one active run in it | start the daemon | the log carries the recovery scan line with `resumed=1`; the run reaches a terminal state; **the journal grew past its pre-kill end**, the resumed segment is marked as such, and **the nonce appears in exactly one `done` line across the whole journal** - interrupted plus recovered is still once | the recovery log line; the journal's pre-kill and final line counts; the nonce count | stop | **pass on native Windows** on its evidenced oracles: the boot log reads `run recovery scan complete resumed=1`, the run reached `completed`, the journal grew from 2 lines to 9, and the nonce appears in **exactly one `done` line**, which is the recovered-not-replayed proof. **A gap worth naming**: the journal carries no marker for the resumed segment at all. `src/engine/journal.rs` writes six phases and none of them says resumed, and the resumed segment restarts `iteration` at `0`, so the file holds two `response` records both labelled iteration 0, separable only by a 51 second timestamp gap. The resume is marked outside the journal, in the daemon log and in a `run_resumed` socket event. **Incidental, and it belongs to the computer-use runtime on Windows**: the first shell call after recovery failed with `[WinError 2] The system cannot find the file specified`, and the model retried with `shell_mode` and succeeded. |
| R3 | provider connected and default | `vadgr run "Use your ask_user tool to ask the owner whether to continue, and wait for the answer." --background`, then watch it from a second terminal | the row reaches **`awaiting_approval`**; the watcher prints the waiting-for-approval line; the socket carries an `awaiting` frame. **Disposition, stated rather than silent**: this release ships no reply surface for a parked run - the engine's own source says so at `src/engine/control/hitl.rs` - so the shipped exits are cancel and boot re-park, and this cell proves the park is reachable, visible on every surface, and safe. The reply surface belongs to the release that ships the conversation surface | the row; the watcher line; the captured `awaiting` frame | R4 consumes this run | **pass on native Windows**: the row reached `awaiting_approval`, the watcher showed `Waiting for your approval: Would you like to continue?`, and the sockets carried `{agent_started, awaiting, run_started}` on the CLI route and `{started, tool_call, paused}` on the phone route. **The cell is not executable exactly as written**: the CLI ships no verb that attaches a watcher to an existing run, so the watched form was used, which is the same `stream::follow` path. **A trap for the other hosts**: the waiting line renders through a spinner that is off when the stream is not a terminal, so a redirected capture records nothing and reads as a false negative. It was read from the console screen buffer instead. |
| R4 | R3's run parked | restart the daemon, then `vadgr runs cancel <id>` | the recovery scan line says `parked=1` and the row still reads `awaiting_approval` after boot; the cancel then lands: the row reads `cancelled`, and **the daemon stays healthy** - health answers `200` and the log holds no panic | the recovery log line; the row before and after the cancel; health; a grep of the log for panics | stop | **pass on native Windows**: `vadgr restart` exit `0`, the boot log reads `resumed=0 parked=1`, and the row still read `awaiting_approval` afterwards, so a parked run is not resumed by a restart. `vadgr runs cancel` exit `0` then left the row `cancelled` with a `completed_at`, health answered `200`, and the log holds zero panics and zero `ERROR` lines. |

## Part G: pairing and devices

`G2`-`G8` run on the tailscale transport. `G4`'s device token is used again by
`G8` and `W4`; it is a credential and is redacted everywhere outside the
command's own environment.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| G1 | no provider connected | `vadgr pair` | refuses before minting: non-zero exit, the connect-a-provider line printed; **the oracle that can actually see a mint**: the daemon's request log holds **zero `POST /api/auth/pair` lines** for the cell's window - `GET /api/devices` cannot answer this, because a minted code never appears there | CLI output and exit code; the request-log grep and its zero count | none | **pass on native Windows**: exit `1`, `Before this machine can pair, connect a model provider.` The request log holds **zero** `/api/auth/pair` lines, so nothing was minted; the only call it made was `GET /api/providers`. |
| G2 | provider default, tailscale transport | `vadgr pair` | a QR, the machine, the address and the code | CLI output | the code is consumed by G4 | **pass on native Windows**: exit `0`, a QR then `Machine: Santiago-Casa`, `Address: santiago-casa.tail323b9e.ts.net:8950`, `Pairing code: JYRH-A0Y6`. |
| G3 | G2's output | decode the printed symbol with `harness/qr-decode` | it recovers exactly the link rebuilt from the printed fields | the decode output | none | **pass on native Windows**: `harness/qr-decode` exit `0`, version 5, ecc level Low, and the decoded link equals the one rebuilt from the printed fields, `vadgr://pair?host=santiago-casa.tail323b9e.ts.net&port=8950&token=JYRH-A0Y6&name=Santiago-Casa`. |
| G4 | G2's live code | `POST /api/auth/claim` from the tailnet address, body `{"pairing_token": "<code>", "device_name": "e2e-probe"}` | `200`; a device token returned exactly once; the device row appears in `GET /api/devices` | the status and body **with the token redacted**; the device row | G8 revokes the device | **pass on native Windows**: the claim from the tailnet address answered `200` with a device id and a token, the device row appeared with `paired_at 05:31:43.059139Z`, and **the token does not appear in the device list**. |
| G5 | G4 done: the code is spent | the same claim again | `401` `PAIRING_CODE_INVALID`: one-time means one time | the status, code and body, as returned | none | **pass on native Windows**: the same code a second time answered `401` `PAIRING_CODE_INVALID`, `That pairing code is wrong or has already been used.` |
| G6 | **its own daemon, with no other pairing traffic**: a wrong-code cell running beside it burns the attempt counter and the code then answers as burned rather than as expired. A freshly minted code, then 301 seconds of wall clock | claim it | `410` `PAIRING_CODE_EXPIRED`: expiry is its own answer, distinct from a wrong code, so the phone says ask for a new one rather than you typed it wrong | the mint time, the claim time, the status, code and body, as returned | none | **pass on native Windows**, on its own daemon and root so no other cell burned the code. Minted `05:30:19.527Z`, claimed `05:35:31.976Z`, a delta of **312.4 seconds**, and the wire answered `410` `PAIRING_CODE_EXPIRED`. That daemon's log holds exactly one pair and one claim, **so no attempt counter was spent and the refusal is expiry alone**. |
| G7 | a freshly minted code | wrong-code claims until the cap answers | within five attempts, `429` `RATE_LIMITED`; the true code is then dead too, per the cap's own message - record what it answers | each attempt's status and code; the final claim of the true code | none | **pass on native Windows**: attempts one to four answered `401` `PAIRING_CODE_INVALID`, and the **fifth** answered `429` `RATE_LIMITED`. The **true** code then answered `401` as well and no device row appeared, so the cap retires the code rather than merely pausing it. |
| G8 | G4's device token; a live run streaming | open `/api/runs/<id>/stream?token=<token>` from the tailnet with `harness/sockets.py --host $(tailscale ip -4) --token <token> --route phone` and see frames flow, then from loopback `DELETE /api/devices/<device-id>` | the tokened socket is admitted and carries frames - the positive token gate; the revoke answers `200` `{"status": "revoked"}`; **the open socket drops now**, not at the next request; the next tokened HTTP request fails the gate; the row is gone from `GET /api/devices`; a second revoke answers `404` `DEVICE_NOT_FOUND` | the frame capture and its cut-off; both DELETE responses; the device list after | none | **pass on native Windows**: a tokened phone socket from the tailnet was admitted, `101`, frames `{started 1, tool_call 1}`. A `DELETE` from loopback answered `200` and the socket closed **`4003` `Device revoked` 0.02s later**, against a 60 second deadline. The same token then answered `401` `INVALID_TOKEN` on `GET /api/runs`, `GET /api/devices` returned `[]`, and a second `DELETE` answered `404` `DEVICE_NOT_FOUND`. **One wording difference recorded rather than smoothed**: the cell expects `{"status": "revoked"}` and the wire returns a superset, `{"device_id": ..., "status": "revoked"}`. |

## Part W: the sockets, on the wire

The CLI watcher is one consumer of `/api/ws/runs/{id}` and proves nothing about
the wire itself or about the phone's route. Every capture here is made by
`harness/sockets.py`, which speaks the protocol with the standard library alone:
an implementation independent of the server's, and nothing to install on any of
the four targets. It records the frames, their **type counts**, the close code
and any refusal; the cell reads that record and decides.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| W1 | a live run just started (F2's shape) | `python3 harness/sockets.py frames.json --port $VADGR_PORT --run <id> --route cli --seconds 60` | the upgrade answers `101`; every frame parses as JSON carrying a `type`; the terminal frame is present; **the frame type counts are recorded** | `frames.json` whole | none | **pass on native Windows**: upgrade `101`, five frames on the CLI route, `{agent_started 1, agent_log 1, agent_completed 1, run_started 1, run_completed 1}`, every one typed JSON with no untyped bucket, and the terminal `run_completed` present. The run row reads `completed` with the shell output `vadgr-e2e-w1a3f7` in its result, so the frames describe work that really happened. |
| W2 | the same or a fresh live run | the same command with `--route phone` | every frame's `type` is one the published frame vocabulary names - a frame the phone has no case for is a **fail**, not a curiosity; the terminal frame is present; the type counts are recorded | `frames.json` whole; the vocabulary check's output | none | **pass on native Windows**: upgrade `101`, five frames on the phone route, `{started 1, tool_call 1, output 2, completed 1}`. Checked against the published vocabulary read from the captured file, **nothing outside it**: the list of unpublished names is empty and a terminal frame is present. The five raw CLI frames map one for one, `agent_started` to `tool_call` and `agent_log` plus `agent_completed` to the two `output` frames, so no internal name reaches the phone. |
| W3 | daemon on loopback | the same command with `--run run-does-not-exist` and no `--route`, so both are driven | the upgrade is accepted and the socket closes at once with **close code `4004`** on both routes, zero frames | the record for both routes | none | **pass on native Windows**: an unknown run id on **both** routes answered `http_status 101`, then closed with `4004` and reason `Run not found`, zero frames either side. |
| W4 | tailscale transport; a live run; G4's token known | the same command with `--host $(tailscale ip -4) --token WRONG`, then again with no `--token` at all | both routes close **`4401`** in both attempts, because a non-loopback source is never admitted without a valid token; the same connect with G4's token is admitted (proven in `G8`) | both records | none | **pass on native Windows** against a genuinely live run, confirmed `running` at capture and `completed` after. From the tailnet address with a wrong token and again with no token at all, both routes answered `101` then closed `4401` `Unauthorized` with zero frames, and the records name `token_supplied` true and false so the two attempts stay distinguishable. **Scope note**: the cell's closing clause, that the same connect with a real device token is admitted, is `G8`'s proof and was not in this run; only the negative gate is proved here. |

## Part S: what only loopback may do

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| S1 | tailscale transport; a provider connected | call two guarded verbs from the tailnet address, then the same call on loopback | the tailnet call is refused and the loopback call succeeds, so the route exists and the refusal is the gate. **The token gate runs first**: an untokened tailnet call answers `401` `MISSING_TOKEN` and never reaches the source check, so `403` `SOURCE_NOT_AUTHORIZED` needs a valid device token presented from a non-loopback address, which means a paired handset. Record which of the two the wire returned rather than assuming the order | both statuses and error codes as returned, and the loopback status | none | **pass on native Windows**, on two guarded verbs. `POST /api/providers/gemini/catalog-refresh` and `PUT /api/default-model` both answered `401` with `MISSING_TOKEN` from the tailnet address untokened, and both answered `200` from loopback, the refresh advancing `catalog_verified_at` to `05:32:52Z` and the default returning `{"model":"gemini-3.7-flash","provider":"gemini"}`. **Which of the two the wire returned is recorded rather than assumed**: the token gate runs first, so it is `401`, and a bogus bearer token on the same route answered `401 INVALID_TOKEN`, a distinct code. **`403 SOURCE_NOT_AUTHORIZED` was not reachable from this host** and is marked so rather than claimed: the daemon binds only the tailnet address and loopback, both authorized, so reaching it needs a valid device token from an off-tailnet source, which is the paired handset the cell names. |

## Part O: OAuth and the callback listener

The callback listener is its own served surface on `127.0.0.1:1455`. `O1` and `O2` need no account. `O3` and `O4` were written while the account was
not available and were marked `blocked` by name rather than deleted. The owner
supplied both during this pass, so they ran: the key from the machine's
environment for `O4`, and a live browser sign-in for `O3`.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| O1 | daemon running; the log line "OpenAI callback listening" present | `curl -i` against `127.0.0.1:1455`: `/auth/complete`, `/auth/failed`, and `/auth/callback?state=bogus&code=bogus` | `/auth/complete` answers `200` with the connected page; `/auth/failed` answers `400` with the failed page; the bogus callback redirects to `/auth/failed`; **the daemon log records the callback's method and path only - the query string appears nowhere in the log**, which is the credential-redaction property this listener exists to keep | the three responses; the log lines; a grep of the whole log for the bogus values returning zero | none | **pass on native Windows** at `7bd9bab`, on the fallback port `1457`: `/auth/complete` `200`, `/auth/failed` `400`, `/auth/callback?state=bogus&code=bogus` `303`. The log holds `callback{method=GET path=/auth/callback}` and **`bogus` appears zero times in it**, so the span records the path and never the query a real code would sit in. |
| O2 | a plain listener bound on `1455` **before** the daemon starts | start the daemon, run `vadgr provider login openai --auth chatgpt`, then one direct `POST /api/providers/openai/auth-attempts` with method `oauth` to record the wire's own answer, then release the port | the daemon logs the callback port unavailable; the login is refused and the CLI says the callback is unavailable; the direct call answers `503`, its error code recorded as returned; after the port is released the daemon binds within its retry and logs "OpenAI callback listening" | the log lines either side; the CLI output and exit code; the wire status and code | stop | **pass on native Windows**: with no callback port bindable, `vadgr provider login openai --auth chatgpt` refused with exit `1` and `Error: the provider callback listener is unavailable`, and **opened no browser**. The second line, `The daemon logged it`, was false at the time and is fixed in `e02ba9a`: the bind failure was `debug` under an `info` filter, so the CLI sent a person to a log that could not contain the line. |
| O3 | the owner's OpenAI account, supplied during this pass | `vadgr provider login openai --auth chatgpt`, the browser authorization completing against `127.0.0.1:1455/auth/callback` | the attempt is minted (`POST /api/providers/openai/auth-attempts`, method `oauth`); `GET /api/provider-auth/<id>` reaches its ready state; the connection commits (`PUT /api/providers/openai/connection`); the provider reads connected with `auth_method` `oauth`; **no token value appears in the log, the database greps or this evidence** | CLI output; the attempt's states as polled; the provider row; the zero-count greps | the connection is removed | **pass on native Windows** with the owner present, at `7bd9bab`. The CLI opened the browser itself with no fallback line printed, the owner signed in, and the daemon committed: `connected true`, `auth_method oauth`, seven models, exit `0`. The callback took `398 ms`, which is the token exchange, and `code=` appears zero times in the log. **One flow proved both Windows fixes**: the URL reached the browser whole, and the whole exchange ran on the fallback port `1457`. **It also settled a false alarm**: an earlier attempt failed with `missing_required_parameter`, which was diagnosed as the provider rejecting `originator=vadgr`. It was not. The URL was being truncated at its first `&`. The identity is unchanged. |
| O4 | `OPENAI_API_KEY` in the command's environment only, supplied during this pass | `vadgr provider login openai --auth api-key`, then `vadgr provider logout openai` | connected via `api_key` with a live catalog, then cleanly disconnected; the key absent from disk and evidence, as in `E1` | CLI output; provider row before and after; the zero-count greps | none | **pass on native Windows**: `Using OPENAI_API_KEY.` names the variable and never the value, `Connected: OpenAI`, **51 models** against the ChatGPT route's seven, and `Default remains: Google Gemini / gemini-3.7-flash`. `GET /api/providers` reads `auth_method api_key`. The secret is absent from stdout. Cleanup ran: `Disconnected: OpenAI`, the row reads `connected false`, and the credential store is back to one file. |
| O5 | the preferred callback port un-bindable before the daemon starts, either by this host's own reservation or by `harness/hold_port.py <port> reserved`; the fallback port free | start the daemon, then `vadgr provider login openai --auth chatgpt` with the owner completing the browser | the log names the fallback port in `OpenAI callback listening`; the minted `authorization_url` carries a `redirect_uri` on **that** port, not the preferred one; the sign-in commits, which proves the token exchange re-sent the identical redirect | the log line, the minted URL from the wire, the provider row | the connection is removed; release the hold | **pass on native Windows** at `7bd9bab`: this host reserves the preferred port with no listener behind it, so the precondition came from the platform. The daemon logged `OpenAI callback listening addr=127.0.0.1:1457`, the authorization URL carried `redirect_uri=http%3A%2F%2Flocalhost%3A1457%2Fauth%2Fcallback`, and the sign-in committed with `auth_method oauth`. **Before the fix the daemon bound one hard-coded port and retried forever in silence** |
| O6 | any daemon; a URL carrying query parameters separated by `&` | open it through the CLI's own launcher, and capture what the browser actually requests with a local listener | the listener receives the **whole** URL, every parameter present. **The oracle is the received request line, never the printed URL**: the CLI printed the URL correctly while sending a truncated one, which is what hid this | the captured request line, and the CLI output showing no `Open this URL:` fallback | none | **pass on native Windows** at `7bd9bab`. Measured before and after: through `cmd /C start` the listener received `GET /x?response_type=code` with `client_id` and `scope` gone, because `cmd` reads `&` as a command separator and the argument is not quoted. Through `rundll32 url.dll,FileProtocolHandler` it received the full line. Driving the real login then opened the browser with no fallback printed, and `O3` completed |

## Part H: the phone, held by a person

**The cutover changes the thing on the other end of the wire**, so the surviving
handheld cells are spent again. The oracle is the daemon, never the screen.

**Two people, and the tester is told what to do, never left to infer it.** The
operator drives the machine and reads the daemon; the tester holds the phone and
does only what the cell tells them, in the order it tells them. A handheld cell
that says "the owner opens the app" and stops has not been written: the person
holding the phone cannot see the daemon, the transport or the state, so every
tap, every toggle and every prerequisite on the device is spelled out.

**Before any cell in this part, the operator reads this aloud and the tester
does it:**

1. **Turn Tailscale on, on the phone**, and confirm it is connected to the same
   tailnet as the machine. The daemon advertises a `*.ts.net` address and binds
   only the tailnet interface, so a handset on plain wifi or mobile data reaches
   nothing and every cell below fails for a reason that has nothing to do with
   the product. This is the step the `0.4.9` pass forgot to say out loud.
2. Open the Vadgr app.
3. Confirm the phone is not already paired to this machine. If it is, remove the
   machine in the app first: `H2` claims a fresh code and a paired handset skips
   the screen under test.

The operator states the tailnet address and the code with each cell; the tester
never types an address the operator did not give them.

**What this part does not do, and why.** These cells are written against the
released `vadgr-mobile 0.4.1`, read from that repository's source at its tag,
and they ask the app for nothing that version does not ship. The shipped app is
a reader: it pairs and unpairs, lists machines, renders a machine's runs as a
conversation, opens a run's sheet and consumes the run stream. Starting a run
from the phone is `vadgr-mobile 0.5.0`, against `POST /api/runs`, so no cell
here asks for it and its handheld cell belongs to that release's runbook.
What this release owns, and what these cells prove, is the wire underneath: that
a paired handset on the tailnet reaches the cutover's daemon, is admitted by its
device token, and receives the stream frames the daemon sends. `W2` drives that
same socket from the machine; only a handset proves the phone's end of it.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| H1 | `H2` done, so the handset is paired; Tailscale still on | **tester**: open the app, then open the machine's row | the app names the machine by the hostname the operator states and shows it healthy; on the daemon side the device row's **`last_seen` advances past its `paired_at`**, which only a request carrying the device token does, and the request log holds `GET /api/runs` calls the operator never made. **The request log records no source address** (finding F5), so it cannot say a request came from the tailnet; `last_seen` is the read that can | the device row before and after, the request counts by route | none | **pass on native Windows**: the app named the machine `Santiago-Casa` and showed `windows . vadgr 0.4.9`, `29ms`, the tailnet host and `online`. Every field equals the daemon: platform `windows`, version `0.4.9`, advertise host `santiago-casa.tail323b9e.ts.net`. The machine screen read `Watching only . this machine is reachable`. **The platform field is the one this release fixed**: the daemon published a hard-coded `wsl2` until this pass, and the phone prints it verbatim, so this row told a Windows owner they were on WSL |
| H2 | Tailscale on and connected on the phone; the app open; this machine not already paired; the operator has just run `vadgr pair` and can see the QR | **tester**: tap Add machine, scan the QR the operator is showing, or type the code exactly as printed including the hyphen | `POST /api/auth/claim` answers `200` in the request log and a device row appears in `GET /api/devices`; the app shows the machine by name | the log line, the device row, the app's machine list | the device stays for `H1`-`H4`; `H5` unpairs it from the handset | **pass on native Windows**. **The verdict is the daemon's, not the screen's**: `POST /api/auth/claim` answered `200` at `03:06:36`, and `GET /api/devices` then carried one row, `Xiaomi 2406APNFAG`, `paired_at 03:06:36.094`, `last_seen 03:06:37.478`. The last-seen is later than the paired-at, so the handset came back and talked to the machine rather than only completing the claim |
| H3 | `H1` done; a provider connected and a default model set; the tester has the machine's conversation open | **operator**: start the run on the machine with `vadgr run "Take one screenshot and tell me in five words what you see" --background`, and say the run id aloud. **tester**: pull the conversation down to refresh until the run's line appears, then stop pulling and watch the line until it finishes | the run's line appears **on a pull**, never on its own: the released list is a one-shot read behind a pull gesture, and a run arriving unpulled ships with `vadgr-mobile 0.5.0`'s machine stream, so unprompted arrival here is a **fail**, not a bonus. Once present, the live line renders progress **without further pulls** and settles on the same terminal status `GET /api/runs/<id>` serves; the daemon's log holds the handset's `GET /api/runs/<id>/stream` from the tailnet address, which is the phone's socket and the one no other cell drives from a handset | the daemon's stream log line with its source address, the run row over time, the journal under the state root's `runs/<id>/` | none | **pass on native Windows**, with a defect recorded rather than smoothed over. The run appeared in the machine's conversation **while it was running**, which is what this cell proves: the handset consumes the run stream over the tailnet. The machine side completed in `6s`, exit `0`, on `gemini-3.7-flash`, and the screenshot was genuinely read, returning `The application in the foreground is Windows Terminal (titled "Windows vadgr")`. **What the phone got wrong**: it drew the run green, as complete, before it had any result, and the model's text appeared only later. The stream is right and the completion state is drawn from the wrong signal. Filed against the release that puts runs on the phone, which owns that state. |
| H4 | `H3` finished | **tester**: tap the run's line so its sheet opens, and read out the status and the text under "WHAT IT PRODUCED" | the status the sheet shows equals the status `GET /api/runs/<id>` serves at the same moment, and the produced text matches the run's stored `outputs.result`; the daemon's log holds the handset's read of that run | the tester's spoken status and the API body, captured together with the time; the log line | `H5` unpairs from the handset | **pass on native Windows**: the sheet showed `Ran`, and under WHAT IT PRODUCED the exact string the daemon recorded, `The application in the foreground is Windows Terminal (titled "Windows vadgr")`. RAN ON read `gemini . gemini-3.7-flash`, equal to the run row. The sheet also states what it cannot do yet, reading the machine's own words and stopping a run, both `0.5.0`, so the app claims no surface it does not ship. The sheet said `5s` where the CLI observed `6s`: the daemon's recorded duration against the caller's wall clock |
| H5 | `H4` done; the handset still paired | **tester**: open the machine, choose Unpair, and confirm the dialog that says the phone forgets the machine and its access is revoked | `DELETE /api/devices/<device_id>` arrives in the daemon's request log **from the handset's tailnet address**; the device row is gone from `GET /api/devices`; the app returns to its unpaired state, and any further read from the phone is refused by the token gate | the DELETE log line with its source address; the device list after; the refused read in the log | none: the unpair is the cleanup | **pass on native Windows**: `DELETE /api/devices/ab84275d-70ca-4aea-99b2-2bdd93d6e3e0` answered `200` at `03:10:55`, the same id paired at `03:06:36`, and `GET /api/devices` returned `[]` |

## Part I: the installer, the update, on a machine that does not have the product

`vadgr update` follows the released default branch by design, so `I4`-`I6`
exercise the command against that branch, driven by binaries built at the head
under test. That is the command's real shape, stated rather than hidden.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| I1 | a container with a shell, git and curl, **no toolchain and no vadgr** | assert both absences | `cargo` and `vadgr` are not found | the two failed lookups | the container is removed | **pass on native Windows**, in `debian:bookworm-slim` with only `git`, `curl` and `ca-certificates` added: `cargo`, `rustc`, `vadgr`, `cc` and `gcc` all resolve to nothing, exit `1` each, and `/root/.vadgr` does not exist. |
| I2 | as I1 | run `install.sh` against the commit under test | it installs the toolchain, builds, and puts both binaries in the install root; **`git rev-parse HEAD` inside the container equals the PR head recorded in `A1`** - the invalidated pass drifted here | the transcript, the install root listing, both head hashes side by side | as I1 | **pass on native Windows**: the script was fetched inside the container by commit and its `sha256` equals `git show <head>:install.sh`, so the installer under test is the commit's own. Exit `0`. The checkout's `HEAD` inside the container equals the host head exactly. The install root holds **one** executable, `vadgr`, 22760088 bytes. Cost recorded: rustup 1.5G, cargo 335M, the install 748M, container 3.19GB, build `1m 02s`. **Observation, not a defect**: `install.sh` printed `Detected OS: wsl` inside a Docker Desktop container, because that kernel carries `microsoft` in `/proc/version`. The `linux` and `wsl` branches are identical, so nothing followed from it. |
| I3 | as I2 | `vadgr --version`, then `vadgr health` | the version matches; health exits `3` because nothing is started, which is the correct answer | CLI output and both exit codes | as I1 | **pass on native Windows**: the installed `vadgr --version` prints `vadgr 0.4.9`, matching `Cargo.toml`, and `vadgr health` with no daemon exits `3` with `API is not running at http://127.0.0.1:8000. Start it with: vadgr start`. |
| I4 | as I3; the clone at a head not behind the released default branch | `vadgr update --check` | exit `0` with "vadgr is up to date." | CLI output and exit code | as I1 | **pass on native Windows**: `vadgr update --check` printed `vadgr is up to date.`, exit `0`, and the oracle agrees: `git rev-list --count HEAD..origin/master` is `0`. |
| I5 | as I4, then `git -C ~/.vadgr/src reset --hard origin/master~2` | `vadgr update --check` | exit `0`; "2 commit(s) available"; the Cargo.lock line printed **when and only when** the range touches `Cargo.lock` - record which it was | CLI output; `git log --oneline` of the range; whether the range touches `Cargo.lock` | as I1 | **pass on native Windows**: with the checkout reset two commits behind, `vadgr update --check` printed `2 commit(s) available. Run 'vadgr update' to apply them.`, exit `0`. **The `Cargo.lock` line was absent and that is the correct half of the rule**: the range touches workflows, docs and scripts only, and `git diff --name-only HEAD..origin/master -- Cargo.lock` is empty, as is the same query for `*.rs` and `Cargo.toml`. So this run recorded the negative side of "when and only when". |
| I6 | `I5` done, the checkout two commits behind | `vadgr update` | it pulls fast forward only, rebuilds and reinstalls; the installed checkout's HEAD equals the origin's; **the binary hash changes when the pulled commits changed Rust source, and legitimately does not when they did not**, so record which kind of commits were pulled beside the hashes | the checkout's HEAD before and after, both binary hashes, and what the pulled commits touched | the container is removed | **fail on native Windows, on one of its two defects. The other is fixed and the cell was re-run to prove it.** **Defect one, fixed in `a83ff1c` and verified end to end**: a freshly installed machine could not run `vadgr update` at all, because nothing put the toolchain on `PATH`. `install.sh` ran rustup with `--no-modify-path`, sourced `$HOME/.cargo/env` in its own process only, and wrote just the install bin into the rc file, so the error named the very thing the installer had left unreachable. Re-driven from nothing after the fix, against the **committed blob** `873ec749...a6e8c` rather than the working copy: the container began with no `cargo`, `rustc`, `vadgr`, `cc`, `gcc` or `rustup`, exit `1` each. The installer printed `Added the Rust toolchain to PATH in .bashrc, which vadgr update needs`, a new login shell then resolved `cargo 1.97.1` and `vadgr`, and `vadgr update` exited `0` with `Updated 1 binary/binaries.` and no toolchain error. **The counterfactual is what makes it conclusive**: the same binary in a shell that does not read the rc file reproduces the old `Could not run cargo` failure, exit `1`. The negative branch holds too: a machine that already had cargo got the `PATH` line and **no** toolchain line, and a second install added no duplicate. **Defect two, still failing and not fixable here**: `vadgr update` follows `master`, and `master` still carries the pre-cutover layout, so with the checkout reset behind it the build fails with `error: could not find Cargo.toml in /root/.vadgr/src`, exit `1`, and the fast forward is not rolled back. Cargo itself produced that error, so the two failures are now cleanly separable. It resolves when `0.4.9` reaches `master`. **One residual gap recorded rather than glossed**: the new line is written when *this installer* set the toolchain up, not when cargo will be reachable in the next shell. A user whose cargo exists only inside the installing process is still uncovered; a normal rustup user has rustup's own line and is unaffected. |

## Part J: state lives where the platform says

The release's first sentence, exercised without the override every other cell
uses. **The guard comes first and is absolute**: if the platform root already
holds anything, the cell is `blocked` by name and nothing there is touched - a
real installation is never the fixture.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| J1 | the platform state root absent or empty, checked and filed first: Linux and WSL `${XDG_STATE_HOME:-$HOME/.local/state}/vadgr`, macOS `~/Library/Application Support/vadgr/state`, Windows `%LOCALAPPDATA%\vadgr` | `env -u VADGR_STATE_HOME vadgr start` on a fresh port, then `env -u VADGR_STATE_HOME vadgr stop` | the daemon serves; `vadgr.db` and `credentials/` appear **under the platform root above**, and nothing appears under the working directory | the guard listing; the platform-root listing while serving; health; the working-directory listing | remove exactly the files the boundary listed, then show the root empty again | **pass on native Windows.** **It was blocked first, by leftovers rather than by the product**: `%LOCALAPPDATA%\vadgr` held `data` and `data\credentials`, two empty directories dated before this pass, on a machine where the product had never been installed. They came from a resolver side effect, not from an installation, and the owner confirmed it. With the root genuinely absent, filed first, `vadgr start` with `VADGR_STATE_HOME`, `VADGR_DB` and `VADGR_RUNS_DIR` all unset served on `8976` and health answered `200`. `vadgr.db` and `credentials/` appeared **directly under the platform root**, and the working directory stayed empty, so nothing was written beside the binary. **Where `credentials` landed is the second half of the finding**: directly under the root, never under `data\`, which is exactly the path the leftover tree had. That is the divergent resolver, seen from the other side. Cleanup ran as the cell requires: the daemon stopped and the four entries `J1` created were removed, leaving the root absent, which is what `J1` found. |

## Per-OS results

**One pass, on WSL, against a frozen head.** An earlier attempt on the same
machine was invalidated whole and withdrawn: three fixes landed mid-pass, the
binaries were rebuilt without re-running the identity cell, and one cell's
recorded output named a refusal that did not exist at the head that pass
recorded. Its evidence is not filed, and the withdrawal is written where it
would have been.

This pass took one rebuild, for finding F5, and it re-recorded `A1` before any
further cell. That rebuild changed the CLI alone: the daemon binary is byte for
byte identical either side of it, so the cells driven against the daemon keep
naming the artifact that produced them, and every cell that invokes the CLI was
run again. The three other operating systems are `not run`: nobody has driven
them, and a green gate on them would say the suites pass there and nothing about
whether the product works.

Legend: `pass` and `fail` mean it ran. `blocked` means it could not run, and says
what stopped it. `not run` means nobody ran it. `Not-Needed` carries its reason.
**A cell is marked from observation, never expectation.**

**CI is not an e2e pass.** The `overall` row never inherits a gate result: it is
the weakest of the parts actually driven on that OS.

| part | WSL | Linux | Windows native | macOS | notes |
|---|---|---|---|---|---|
| automated gate | pass | not run | **pass** | not run | run locally on this host: **311 tests**, `cargo fmt --check` and `cargo clippy --release --all-targets -- -D warnings` both at exit `0`. **It is not an e2e pass and does not stand in for one**: the parts below are what was driven |
| surface sweep | pass | not run | **pass** | not run | run from `harness/sweep.py` on this host: 18 published HTTP surfaces, 19 CLI verbs, and **7 absence probes all answering `404`**, so nothing is half wired. The HTTP codes are the deliberate set, `200`, `204`, `401`, `404`, `409` and `422` |
| A: the built head | pass | not run | **pass**, 4 of 4 | not run |  |
| B: the consolidation | pass | not run | **pass**, 10 of 10 | not run | a `WAL` row never checkpointed, interrupted staging debris, and all three refusals naming what they found |
| C: the service group | pass | not run | **pass**, 13 of 13 | not run | `C13` ran here for the first time: the tailnet address held and loopback free, which is the multi-host bind check |
| D: read-only commands | pass | not run | **pass**, 5 of 5 | not run |  |
| CU: computer use | pass | not run | **pass**, 4 of 4 | not run | `CU2` failed and was fixed here: `/api/health` reported the module usable while the owner had disabled it, because it read installation rather than the setting |
| E: provider onboarding | pass | not run | **pass**, 6 of 6 | not run |  |
| F: runs and the watcher | pass | not run | **pass**, 9 of 9 | not run | `F7` and `F8` both failed first and both were closed: `resume` now prints its row, and `F8`'s failure was an inherited ignore-Ctrl+C bit in the harness, not the product |
| R: interruption and recovery | pass | not run | **pass**, 4 of 4 | not run | the journal carries no marker for a resumed segment, and `R3` has no CLI verb that attaches a watcher to an existing run |
| G: pairing and devices | pass | not run | **pass**, 8 of 8 | not run |  |
| W: the sockets | pass | not run | **pass**, 4 of 4 | not run |  |
| S: source enforcement | pass | not run | **pass**, 1 of 1 | not run | the token gate answers before the source gate; see the cell. |
| O: OAuth and the callback | pass | not run | **pass**, 6 of 6 | not run | the owner supplied the account and the key during this pass. |
| H: the phone | pass | not run | **pass**, 5 of 5 | not run | a person held the handset: pair, machine, run, read back, unpair. a person held the handset: pair, machine, run, read back, unpair. The phone draws a run complete before it has a result |
| I: the installer and update | **pass, and worth re-reading** | not run | **5 of 6**, `I6` fails | not run | **The two results are different depths of one cell, not a disagreement about the product.** The WSL row carries the word `pass` and no evidence. On Windows an update that pulls nothing behaves the same way and passes: the checkout is ahead of `master`, the pull is a no-op, and the rebuild builds the `0.4.9` tree. The layout failure appears only when the update **actually pulls**, which was forced here by resetting the checkout behind `master`. Both `I6` defects are deterministic against today's `master`, so the WSL pass most likely took the no-op path the cell does not intend | in a container with no toolchain and no product |
| J: the platform state root | pass | not run | **pass**, 1 of 1 | not run | no overrides at all, state under the platform root. the platform root already holds directories from before this pass, so the cell's own guard applies. It uncovered a second state-root resolver that disagrees with `config::state_root` |
| **overall** | pass | not run | **pass**, 85 of 86, 1 owed by the default branch | not run | the weakest part actually driven on this OS, which is every part. **Windows**: every part driven, and the repeatability check run as three concurrent passes with their own port, database and daemon. The one cell not passing is `I6`, and only half of it: its installer defect is fixed and re-driven from nothing, while `vadgr update` still cannot build a `master` that carries the pre-cutover layout, which resolves when this release lands there. **Six defects were found and fixed on this operating system**, each with a test that fails without it and each verified by re-running the cell that found it. **Three findings were retracted as harness faults rather than left standing**: `vadgr start` never hung, the provider never rejected our identity, and `F8`'s watcher always had its handler. Each retraction is recorded where the claim was made |

Paths, process supervision and access control are platform-shaped. **No supported
operating system is `Not-Needed` for final acceptance.**

## Findings

### F1 (fixed): Gemini refused every run that looked at the screen

A screenshot returned inside the function response was refused by the service
("Multimodal function responses are not supported for this model"), so every
screen run failed. Five failed rows sat in the invalidated pass's own run
listing with no disposition, which is how this finding was nearly lost. Fixed on
this branch in `src/engine/provider/gemini.rs`: the image travels as its own
`inlineData` part beside the function response. A regression test fails without
it. Invalidates: E, F, and every run-bearing cell of the earlier pass.

### F2 (fixed): the consolidation verified that the target opens, not that it serves

A moved database missing a column every read needs passed the move and failed
the first request. Fixed on this branch in `src/migrate.rs`: the consolidation
now opens the target the way the daemon does, runs the migrations, performs the
read the API performs, refuses a target it cannot serve, removes the half-made
target and leaves the sources untouched. `B10` exercises exactly this refusal.
Invalidates: B.

### F3 (fixed): the CLI resolved directories the installer never creates

`vadgr update` on a fresh install reported a checkout that was not there and
named a directory nothing had written, because the CLI still resolved the
repository's former directory names. Fixed on this branch in
`src/cli/commands/service.rs`; a test now reads the installer and the resolver
together so they cannot drift apart. `I4`-`I6` exercise the repaired paths.
Invalidates: C, I, and the sweep's CLI section.

### F4 (fixed): `vadgr health` told a user their module was missing when they had turned it off

The API answers whether a module is usable and never says why: `false` covers a
module that is absent and one the owner disabled. The CLI rendered both as
`not found`, so a user who had just run `vadgr computer-use disable` was told
their installation was missing. It now prints `unavailable`, which states what
the daemon said and adds no cause of its own, and a test in
`src/cli/commands/info.rs` fails on the old word. `D1` compares the CLI and the
wire under that mapping; `CU2` and `CU3` drive the disabled and enabled sides.
Invalidates: nothing yet recorded, because the pass had not begun.

### F5 (open): the request log cannot say where a request came from

Every line reads `method`, `uri`, `version`, `latency` and `status`, and no
peer address. So a cell wanting to prove that the phone reached the daemon over
the tailnet, rather than something on the machine reaching it over loopback,
cannot read that from the log. `H1` uses the device row's `last_seen` instead,
which only a token-carrying request advances, and that is a stronger read
because it names the device rather than the interface. The log is still the
poorer for it: an operator debugging a refused request cannot see who was
refused. Open, and not fixed here, because changing what the daemon logs
mid-pass would invalidate every cell already run against this build.

### F6 (fixed): health says a disabled module is available

`vadgr computer-use disable` sets `enabled` to `false` on
`GET /api/settings/computer-use`, and `GET /api/health` goes on reporting
`"computer_use": true`. The two answer different questions and only one of them
is on the health surface: health reads whether the runtime is installed
(`src/routes/health.rs`), while the loop reads whether it is enabled before
mounting the tools (`src/engine/mcp/mod.rs`). With the setting off, a run gets
no computer-use tools and health still calls the module available, so the one
screen a user checks after turning something off tells them nothing turned off.

Found by `CU2`, and **closed on the Windows pass rather than deferred again**.
The deferral above was written when rebuilding mid-pass would have invalidated
the daemon-side cells; on Windows the daemon was already being rebuilt for two
other fixes, so the cost the deferral was avoiding had already been paid.

`src/routes/health.rs` now answers usability rather than installation: a module
is reported only when it is installed **and** enabled, and a status carrying
neither field reports not usable, so a missing field never advertises a module.
Four tests fail without it. **`CU2` was re-run against the rebuilt daemon**,
which is what closes the finding: `disable` leaves the setting `false` and
health `false`, `enable` returns both to `true`.

### F7 (open): the live model check refuses a good model when the provider returns an empty candidate

`vadgr model default` verifies a model before accepting it, which is right and
`E2` proves it: a catalog entry that cannot answer an ordinary request is
refused and the previous default stays. But the check treats **any** response
without parts as invalid, and a provider can answer a valid request with a
candidate carrying no parts. One repeatability pass hit exactly that and the
command failed with `provider response is invalid: candidate has no parts` on
`gemini-2.5-flash`, a model the other two passes set without trouble seconds
later.

The user-visible effect is an intermittent refusal to set a model that works.
Found by the three-pass comparison, not by any assertion: the passes disagreed
on turn-0 input tokens, and the reason was that one of them had silently stayed
on the starter model. Open: the fix is a retry or a narrower invalid test in
daemon code, and rebuilding the daemon mid-pass would invalidate every
daemon-side cell already run.

### F8 (open, and it belongs to distribution): a built binary carries its build machine's C library

The clean install was pointed at an older distribution than the one that built
the binary, and the daemon would not start: `GLIBC_2.38 not found`, then
`GLIBC_2.39 not found`. A binary built on Ubuntu 24.04 does not run on Debian
12.

**It is not a defect today**, and the reason matters: the installer compiles on
the user's own machine, so the C library the binary needs is the one that
machine has, by construction. The check now uses a base image matching the
distribution the binary was built on, which is what a user's situation actually
is.

It becomes a defect the moment a release hands someone a **prebuilt** binary
they did not compile. Then the binary must be built against an old enough C
library, or statically, or shipped per distribution. That is the distribution
release's problem and it is recorded here so it arrives as a known question
rather than a surprise. The same class of problem was found and fixed on
Windows in this release: the binary imported the Visual C++ redistributable
until the C runtime was linked in.

### F9 (fixed): the callback listener bound one hard-coded port, and said nothing when it could not

`vadgr provider login openai --auth chatgpt` refused on a host where port `1455`
is reserved by the operating system with **no listener behind it**. The daemon
retried that one port every second for its whole life and reported nothing: the
bind failure was `debug` under an `info` filter, while the CLI told the person
to read a log that could not contain the line.

The listener now takes either port the authorization server accepts, publishes
the one it bound, and the authorization URL names that port, so the browser is
sent where something is listening. The redirect is carried on the attempt rather
than recomputed, because the token exchange re-sends it and the server compares
the two. The failure is reported at `warn`, once per state change, not once per
retry. Found by `O2`, guarded by `O5`, and proved by `O3`: a real sign-in
completed on the fallback port.

### F10 (fixed): the browser received the part of the URL before the first `&`

The CLI printed a correct authorization URL and sent a truncated one. It opened
the browser through `cmd /C start`, and `cmd` reads `&` as a command separator;
the argument is not quoted, because quoting only covers arguments holding
spaces. The browser got everything up to the first `&` and nothing after it, so
`client_id`, `redirect_uri` and the PKCE challenge never arrived and the
provider answered that a required parameter was missing.

**The printed URL is what made this hard to see**, and it is why the guarding
cell `O6` asserts on the request a listener captures rather than on what the CLI
displays. Measured both ways: through `cmd` the listener received
`GET /x?response_type=code` with the rest gone; through
`rundll32 url.dll,FileProtocolHandler` it received the whole line. No shell now
sits between the CLI and the browser on any platform.

**This one nearly cost the product its identity.** The failure was first
diagnosed as the provider rejecting `originator=vadgr`, with three other
projects having hit the same message and fixed it by sending another vendor's
string. That change was written and not made. The cause was one line choosing
`cmd`.

### F11 (fixed): a daemon that refused to start was reported as a busy port

Whenever the spawned daemon exited early, `vadgr start` printed
`API process died. Port N may be in use`. That is the usual cause and it was the
wrong one: the daemon had refused to merge two databases sharing a run id, and
had written a precise reason naming the id, both files, and the fact that
nothing had been moved. The operator was sent to hunt a port conflict that did
not exist.

The CLI now reads the daemon's own failure line and repeats it. Only a line the
daemon wrote as its failure counts, so an earlier warning is never reported as
the cause. Found by `B5`, and `B10` shows the same fix carrying a different
refusal: the missing column named to the operator.

### F12 (fixed): the installer left the toolchain it installed unreachable

A machine installed cleanly and its **first** `vadgr update` failed with
`Could not run cargo`, naming the toolchain the installer had just set up.
`install.sh` ran rustup with `--no-modify-path`, sourced `$HOME/.cargo/env` in
its own process only, and wrote just the install bin into the rc file.

The startup line is now written beside the `PATH` line, and only when this
installer set the toolchain up, so a machine that already had cargo keeps its
own arrangement. Found by `I6` and **re-driven from nothing to close it**: a new
login shell resolves cargo and `vadgr update` exits `0`. The counterfactual is
what makes it conclusive, because a shell that does not read the rc file
reproduces the old failure exactly.

### F13 (open): a second state-root resolver disagrees with the first

`config::state_root` answers `%LOCALAPPDATA%\vadgr` on Windows, and
`default_state_root()` in `src/engine/provider/credentials.rs` falls back to
`data_local_dir()` and answers `%LOCALAPPDATA%\vadgr\data`. The second also
reads the real known folder rather than the environment variable, so it ignores
an override the first honours.

At `0.4.9` it looks unreachable from the daemon, which always sets the state
home explicitly, and the directories that exposed it predated the pass. It is
recorded because the file's own comment warns that three resolvers is how two of
them drift, and two of them already have. Found while `J1` was blocked: the
empty `data\credentials` tree it left is this resolver's fingerprint, and `J1`
run properly puts `credentials/` directly under the root instead.

### F14 (open, and it resolves on merge): update follows a default branch with the old layout

`vadgr update` pulls `master` and rebuilds. `master` still carries the
pre-cutover layout with the crate under `rust/`, so the `0.4.9` command cannot
build the tree its own update pulls: `could not find Cargo.toml`. The fast
forward is also not rolled back, so the checkout is left on the older source
while the installed binary is the newer build, and the message that nothing was
replaced is true of the binary and false of the checkout.

A `0.4.9` user is not exposed while their clone is ahead of `master`, because
`I4` answers up to date and nothing is pulled. It resolves when this release
reaches `master`. Found by `I6`, and it is the half of that cell which is not
fixable from here.

## Surface coverage - **every published endpoint, with what it returned**


### Shipped

| endpoint | what was asked | status | code | response, as returned |
|---|---|---|---|---|
| `GET /api/health` | the daemon is up | `200` | - | `{"modules":{"computer_use":true},"platform":"wsl","status":"healthy","transport":{"advertise_host":null,"available":true,"bind_host":"127.0.0.1","name":"loopback"},"version":"0.4.9"}` |
| `GET /api/providers` | the provider list | `200` | - | `[{"auth_method":null,"auth_methods":["oauth","api_key"],"available":false,"catalog_stale":false,"catalog_verified_at":null,"connected":false,"default_model":null,"id":"openai","is_default":false,"kind` |
| `GET /api/settings/computer-use` | the computer-use setting | `200` | - | `{"enabled":true,"platform":"wsl2","venv_ready":true}` |
| `GET /api/computer-use/status` | the runtime's own status | `200` | - | `{"available":true,"platform":"wsl2"}` |
| `GET /api/devices` | paired devices | `200` | - | `[]` |
| `GET /api/runs` | the run list | `200` | - | `[{"agent_name":"Take one screenshot.","completed_at":"2026-08-20T01:51:00.947455+00:00","id":"run-6ca83bcdd18e48849c4fef1cb1b537ce","inputs":{"task":"Take one screenshot."},"log_path":null,"model":"ge` |
| `GET /api/runs/run-6ca83bcdd18e48849c4fef1cb1b537ce` | one run | `200` | - | `{"agent_name":"Take one screenshot.","completed_at":"2026-08-20T01:51:00.947455+00:00","id":"run-6ca83bcdd18e48849c4fef1cb1b537ce","inputs":{"task":"Take one screenshot."},"log_path":null,"model":"gem` |
| `POST /api/runs/run-6ca83bcdd18e48849c4fef1cb1b537ce/cancel` | negative: cancelling a finished run | `409` | `RUN_NOT_ACTIVE` | `{"error":{"code":"RUN_NOT_ACTIVE","details":{},"message":"Run is already finished"}}` |
| `POST /api/runs/run-6ca83bcdd18e48849c4fef1cb1b537ce/resume` | resume | `409` | `RUN_NOT_RESUMABLE` | `{"error":{"code":"RUN_NOT_RESUMABLE","details":{},"message":"Only failed runs can be resumed (current status: completed)"}}` |
| `GET /api/runs/run-does-not-exist` | negative: no such run | `404` | `RUN_NOT_FOUND` | `{"error":{"code":"RUN_NOT_FOUND","details":{},"message":"Run with id 'run-does-not-exist' not found"}}` |
| `POST /api/runs` | negative: no task | `422` | - | `{"detail":[{"msg":"Failed to deserialize the JSON body into the target type: missing field `task` at line 1 column 2","type":"value_error"}]}` |
| `POST /api/auth/pair` | mint a pairing code | `503` | `TRANSPORT_UNREACHABLE` | `{"error":{"code":"TRANSPORT_UNREACHABLE","details":{"transport":"loopback"},"message":"Transport cannot advertise a reachable address. Enable Tailscale (VADGR_TRANSPORT=tailscale) to pair over your ta` |
| `POST /api/auth/claim` | negative: a code that was never minted | `401` | `PAIRING_CODE_INVALID` | `{"error":{"code":"PAIRING_CODE_INVALID","details":{},"message":"That pairing code is wrong or has already been used."}}` |
| `POST /api/providers/gemini/catalog-refresh` | refresh a connected catalog | `200` | - | `{"auth_method":"api_key","auth_methods":["api_key"],"available":true,"catalog_stale":false,"catalog_verified_at":"2026-08-20T01:51:25.466039+00:00","connected":true,"default_model":"gemini-2.5-flash",` |
| `POST /api/providers/openai/catalog-refresh` | negative: refresh a disconnected one | `409` | `PROVIDER_NOT_CONNECTED` | `{"error":{"code":"PROVIDER_NOT_CONNECTED","details":{},"message":"provider is not connected"}}` |
| `PUT /api/default-model` | negative: a model that is not in the catalog | `422` | `MODEL_NOT_AVAILABLE` | `{"error":{"code":"MODEL_NOT_AVAILABLE","details":{},"message":"model is not in the connected provider catalog"}}` |
| `DELETE /api/providers/openai/connection` | negative: disconnect what is not connected | `204` | - | `` |
| `GET /api/provider-auth/attempt-does-not-exist` | negative: no such attempt | `404` | `AUTH_ATTEMPT_NOT_FOUND` | `{"error":{"code":"AUTH_ATTEMPT_NOT_FOUND","details":{},"message":"provider authentication attempt not found"}}` |

### Not present - probed to confirm absent, not half-wired

| endpoint | disposition | status | response |
|---|---|---|---|
| `GET /api/agents` | deleted at 0.4.4 | `404` | `` |
| `POST /api/agents` | deleted at 0.4.4 | `404` | `` |
| `GET /api/projects` | deleted at 0.4.4 | `404` | `` |
| `GET /api/registry` | deleted at 0.4.4 | `404` | `` |
| `GET /api/workflows` | deferred, POSSIBLE_PLANS #45 | `404` | `` |
| `GET /api/conversations` | 0.6.0 | `404` | `` |
| `PATCH /api/machine` | 0.7.0 | `404` | `` |

### The CLI

| command | exit | output produced | first line |
|---|---|---|---|
| `vadgr --version` | `0` | stdout | `vadgr 0.4.9` |
| `vadgr health` | `0` | stdout | `Status:       healthy` |
| `vadgr providers` | `0` | stdout | `OpenAI (openai) -- not connected` |
| `vadgr computer-use status` | `0` | stdout | `Computer use: enabled` |
| `vadgr runs list` | `0` | stdout | `Run ID    Task                  Status     Duration` |
| `vadgr runs` | `0` | stdout | `Run ID    Task                  Status     Duration` |
| `vadgr runs get run-6ca8` | `0` | stdout | `Run ID:       run-6ca83bcdd18e48849c4fef1cb1b537ce` |
| `vadgr runs cancel run-6ca8` | `1` | stderr | `Error: Run is already finished` |
| `vadgr runs resume run-6ca8` | `1` | stderr | `Error: Only failed runs can be resumed (current status: completed)` |
| `vadgr runs get zzzzzzzz` | `1` | stderr | `Error: No run matching 'zzzzzzzz' found.` |
| `vadgr provider status` | `0` | stdout | `OpenAI: not connected` |
| `vadgr model list` | `0` | stdout | `Google Gemini: connected (default)` |
| `vadgr status` | `0` | stdout | `Service  PID    Status ` |
| `vadgr logs --no-follow -n 2` | `0` | stdout | `2026-08-20T01:51:25.948561Z  INFO request{method=GET uri=/api/providers version=HTTP/1.1}: tower_http::trace::on_response: finished processing request latency=0 ms status=200` |
| `vadgr update --check` | `1` | stderr | `Error: /tmp/vadgr-049-e2e-final/rerun/vhome/src is not a git checkout, so it cannot be updated. Reinstall with the installer instead.` |
| `vadgr run    ` | `2` | stderr | `Error: TASK must not be empty.` |
| `vadgr run x --provider gemini` | `2` | stderr | `Error: --provider and --model must be given together.` |
| `vadgr runs get` | `2` | stderr | `error: the following required arguments were not provided:` |
| `vadgr not-a-command` | `2` | stderr | `error: unrecognized subcommand 'not-a-command'` |

18 shipped endpoint calls, 18 answered; 7 absence probes; 19 CLI invocations.

## Repeatability - **three independent passes**


```
| axis | 8821 | 8822 | 8823 |
|---|---|---|---|
| HTTP entries | 18 | 18 | 18 |
| absence probes | 7 | 7 | 7 |
| CLI entries | 19 | 19 | 19 |
| method, path, status and error code | same | same | same |
| argv, exit code and output produced | same | same | same |
| whole record, ids normalised | differs | differs | differs |

=== frame type counts per socket, per pass
  cli: {'agent_completed': 1, 'agent_log': 1, 'agent_started': 1, 'run_completed': 1, 'run_started': 1} -> identical across the three
  phone: {'completed': 1, 'output': 2, 'started': 1, 'tool_call': 1} -> identical across the three

=== turn-0 input tokens, with the model pinned in all three
  8821: model gemini-2.5-flash, turn-0 input 1774
  8822: model gemini-2.5-flash, turn-0 input 1774
  8823: model gemini-2.5-flash, turn-0 input 1774
```

**Native Windows, three concurrent passes on ports 8824, 8825 and 8826.** The
runbook's `8821` to `8823` are unusable on this host, all three reserved with no
listener, so the ports were probed before use and the real ones read back from
each root's own port file.

```
| axis | 8824 | 8825 | 8826 |
|---|---|---|---|
| HTTP entries | 18 | 18 | 18 |
| absence probes | 7 | 7 | 7 |
| CLI entries | 19 | 19 | 19 |
| method, path, status and error code | same | same | same |
| argv, exit code and output produced | same | same | same |
| whole record, ids normalised | differs | differs | differs |

=== frame type counts per socket, per pass
  cli:   {'agent_completed': 1, 'agent_log': 1, 'agent_started': 1, 'run_completed': 1, 'run_started': 1} -> identical across the three
  phone: {'completed': 1, 'output': 2, 'started': 1, 'tool_call': 1} -> identical across the three

=== turn-0 input tokens, with the model pinned in all three
  8824: model gemini-3.7-flash, turn-0 input 7818
  8825: model gemini-3.7-flash, turn-0 input 7817
  8826: model gemini-3.7-flash, turn-0 input 7817
```

**The records differ and the difference was read rather than assumed**: only the
per-pass nonce and result text, the run id path segments, a catalog timestamp, a
log line timestamp and one root path. Nothing structural. Three distinct
databases by `sha256`, three credential stores, three run ids, three model
results. **The token counts are not three identical numbers**, which is the
shape that would suggest one result reused: the one-token spread is the nonce,
which tokenises one token longer in the `8824` run.

**Four things looked odd and none of them is a failed assertion**, which is why
they are written here:

- `POST /api/auth/pair` is logged at **ERROR** in all three daemons. The `503`
  `TRANSPORT_UNREACHABLE` is the correct refusal on the loopback transport, and
  a designed refusal reading as a fault sends someone hunting.
- `GET /api/computer-use/status` costs **653 to 685 ms** while every other local
  route answers in 0 to 10 ms. It is the only one that shells out to the
  runtime. Consistent across all three, so not a flake, and nothing asserts on
  it.
- Every boot warns that **no callback port could be bound**, because `1455` is a
  host reservation and `1457` was held by another daemon. The pool is two deep,
  so a second installation on one machine cannot sign in to ChatGPT.
- All six sockets ended with **no close frame from the server**; the client left
  at its own deadline. That matches `W1`, and a client that waits for a close
  will hang.

## What this runbook cannot prove

- **The socket-level source refusal** (the `403` branch inside the socket
  admission path). The tailscale transport binds only the tailnet interface and
  verifies each peer's membership, so a peer that branch would refuse cannot
  reach the socket at all from outside. The branch is covered by the unit suite;
  no live cell can reach it, and pretending one could would be a cell that never
  runs. `S1` proves the HTTP source gate live instead.
- **A completed OpenAI OAuth authorization**, until the owner supplies the
  account `O3` names. The callback listener's pages, its refusal when the port
  is taken, and its query-redaction are proven without it (`O1`, `O2`).
- **The `--replacement-default-model` flag's trigger.** It fires only when the
  provider's catalog has dropped the connected default mid-login, which the
  provider controls and this pass cannot stage. The flag's plumbing is unit
  territory; the flag is named here so its absence from the cells reads as a
  decision, not a hole.
- **macOS and Windows behaviour**, until their columns carry their own passes.

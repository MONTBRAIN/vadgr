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
| vadgr-computer-use | 0.7.3 | the installed `vadgr-cua` entry point over stdio, and the screenshot and shell tools, which are the tools every screen-touching cell here uses |

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
| `vadgr-computer-use` installed, `vadgr-cua` resolvable | `CU1`-`CU3`, `F1`-`F3`, `F5`, `R1`-`R2`, `H3` | `vadgr-cua --version` prints a version | none | none |
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
| A the binary is the built head | identity x tree | 3 | 0 | 3 |
| B the consolidation | inputs x outcome | 10 | 0 | 10 |
| C the service group | verb x state x flag | 11 | 0 | 11 |
| D read-only commands | command x state | 5 | 0 | 5 |
| CU computer use | setting x live probe | 3 | 0 | 3 |
| E provider onboarding | verb x live credential | 6 | 0 | 6 |
| F runs and the watcher | outcome x flag | 9 | 0 | 9 |
| R interruption and recovery | kill x boot x park | 4 | 0 | 4 |
| G pairing and devices | mint x claim x revoke | 8 | 0 | 8 |
| W the sockets, on the wire | route x admission | 4 | 0 | 4 |
| S source enforcement | gate x source | 1 | 0 | 1 |
| O OAuth and the callback | page x port x account | 4 | 0 | 4 |
| H the phone, held by a person | what the released app does | 5 | 0 | 5 |
| I the installer and update | clean host x drive | 6 | 0 | 6 |
| J the platform state root | default resolution | 1 | 0 | 1 |
| | | **80** | **0** | **80** |

## Part A: the thing under test is the thing that was built

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| A1 | `$E2E_BIN` first on `PATH` | `command -v vadgr` | resolves inside `$E2E_BIN`; its `sha256` is the release build of the head under test. **Re-run after any mid-pass rebuild, before any further cell** | the path and both hash lines, and the head they were built from | none | pass |
| A2 | as A1 | `vadgr --version` | prints `0.4.9`, matching the manifest. The daemon's own version is asserted at `D1`, where a daemon exists to ask | the printed line and the manifest line | none | pass |
| A3 | a clean checkout | `git ls-files` | **no `.py` file outside `scripts/` and an older runbook's `harness/`**, **no interpreter artefact of any kind**: no `.pyc`, `.pyo`, `.pyd`, `__pycache__/`, `site-packages/` or virtual environment, no `requirements.txt`, no `rust/` directory | the file list, the sweep's own output | none | pass |
| A4 | the install root the installer wrote | list it | **one executable**, named `vadgr`, and no second file beside it. The daemon is this binary invoked with `serve`, so a user receives one artifact rather than two that must stay in step | the directory listing, and the process table of a started daemon | none | |

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
| B1 | an empty state root, no legacy database anywhere | start the daemon | it serves; the root holds `vadgr.db` and `credentials/` | directory listing, health | stop | pass |
| B2 | a legacy database from the departing daemon with two runs, no other | start the daemon | the root's `vadgr.db` holds both runs; the source is gone | the run ids read from the source before, and from the target and `GET /api/runs` after | stop | pass |
| B3 | both legacy databases, different runs in each, and a legacy journal tree | start the daemon | **every run from both** is in the target, the journals are under `runs/`, and both sources are gone | the run ids read from **each source before the move** and from the target after it - three lists, filed; the journal file's bytes | stop | pass |
| B4 | as B3, plus a run committed to the write-ahead log and not checkpointed | start the daemon | that run is in the target too | the row id, read from the target | stop | pass |
| B5 | both databases sharing one run id | start the daemon | **it refuses**: non-zero exit, the id named, and both sources untouched | the message; **the four `sha256sum` lines**, both sources before and after | none | pass |
| B6 | both databases sharing one device id | start the daemon | it refuses and names the device; both sources untouched | the message; the four `sha256sum` lines | none | pass |
| B7 | a target root holding a file this product did not write | start the daemon | it refuses and names the root; the foreign file is untouched | the message; the foreign file's `sha256sum` before and after | none | pass |
| B8 | a staging directory left by an interrupted attempt | start the daemon | the debris is discarded and the consolidation completes | the listing before and after | stop | pass |
| B9 | a machine already consolidated | start the daemon twice | the second start changes nothing: same row count, same file hash | the run count both times; **the two `sha256sum` lines** of the checkpointed database | stop | pass |
| B10 | a legacy database that opens, but whose `runs` table is missing a column every read needs | start the daemon | **it refuses**: non-zero exit, the missing column named, no target left behind, and the source byte for byte as it was | the message; the target's absence as a directory listing; **the source's two `sha256sum` lines** | none | pass |

## Part C: the service group

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| C1 | nothing on the port | `vadgr start` | exit `0`; **the process serving is this same binary invoked with `serve`**, read from the process table rather than from the CLI's output, because the product is one executable and a second file would mean a user had to receive two | CLI output, the `ps` line with its full argument list, health | C4 | pass |
| C2 | C1's daemon running | `vadgr start` | refuses, non-zero, the pid unchanged | CLI output, the pid twice | C4 | pass |
| C3 | as C2 | `vadgr status`, `vadgr logs --no-follow -n 5` | the table names the live pid; the log tail matches the file | CLI output, `tail -5` | C4 | pass |
| C4 | as C2 | `vadgr stop` | the process is gone, the port free, the pid and port files removed | `ps`, listener list, directory | none | pass |
| C5 | a listener holding the port and never accepting | `vadgr start` | it walks up and the port file names the port it took | CLI output, listener list, port file | stop | pass |
| C6 | **a daemon running** | `vadgr restart` | the old pid is stopped, a new pid serves health on the port | both pids, from the process table | stop | pass |
| C7 | stopped, nothing on the port | `vadgr restart` | prints the not-running line, then starts: exit `0`, a daemon serves health | CLI output, the new pid, health | stop | pass |
| C8 | stopped, nothing on the port | `vadgr stop` | prints "vadgr is not running.", exit `0`, and creates no pid or port file | CLI output, exit code, the pid directory listing | none | pass |
| C9 | nothing on port `8863` | `vadgr api --port 8863` | the `api` verb starts the daemon on the named port: exit `0`, the port file says `8863`, the process table shows this binary with `serve --port 8863`, health answers on `8863` | CLI output, port file, `ps` line, health | stop | pass |
| C10 | daemon running | `vadgr logs -n 1` (follow is the default), then one `curl` of `/api/health` from another terminal, then interrupt the follow | the followed output gains the request line the log file gained after the follow began; the interrupt ends the follow | the captured follow output and the file's own tail, diffed | none | pass |
| C11 | daemon running | `vadgr logs --service nosuch --no-follow` | refuses: "No logs found for nosuch", non-zero exit | CLI output and exit code | none | pass |

## Part D: the read-only commands

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| D1 | daemon running | `vadgr health` | `0.4.9`, the host's platform, and the module block. **Every field the CLI prints equals the API's value for that field, compared field by field.** The API serves `"computer_use": false` on a fresh root and the CLI must print `unavailable` for it, never a word claiming a cause the daemon did not report (finding F4) | CLI output and the `curl` body, side by side | none | pass |
| D2 | as D1 | `vadgr providers` | the three providers with their state; equals `GET /api/providers` | CLI output, `curl` body | none | pass |
| D3 | as D1, no runs | `vadgr runs list` | "No runs found." and exit `0` | CLI output | none | pass |
| D4 | one run present: this cell is executed after Part F, against F's rows | `vadgr runs list`, `vadgr runs get <prefix>` | the table carries a duration; the prefix resolves; fields equal the API | CLI output, `curl` body | none | pass |
| D5 | nothing listening | `vadgr health` | exit `3` with the daemon-is-down line | CLI output | none | pass |

## Part CU: computer use is a setting the product owns

The run cells need this group: a screen run with computer use off is a different
product. `CU2` before `CU3` so the group ends enabled.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| CU1 | daemon running, `vadgr-cua` resolvable | `vadgr computer-use status` | prints the availability; equals `GET /api/computer-use/status`, whose `available` comes from a live tool listing against the runtime, and `GET /api/settings/computer-use` | CLI output and both `curl` bodies | none | pass |
| CU2 | as CU1 | `vadgr computer-use disable` | exit `0`; `GET /api/settings/computer-use` says `"enabled": false`; `/api/health`'s module block says `"computer_use": false` | CLI output, both `curl` bodies | CU3 | pass |
| CU3 | as CU2 | `vadgr computer-use enable` | exit `0`; the setting reads `"enabled": true` through the API; `GET /api/computer-use/status` reports `"available": true` from its live probe | CLI output, both `curl` bodies | none | pass |

## Part E: provider onboarding

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| E1 | fresh state root; the key in the command's environment only | `vadgr provider login gemini` | names the variable, never the value; the daemon reports Gemini connected with a live catalog; **the key is absent from the database, WAL, SHM and this evidence** - the grep runs against the raw files on disk, and the single expected holder is the credential store file, named with its mode | CLI output, `curl` body, the grep commands and their zero counts, the credential file's name and mode | E3 leaves gemini; the root is removed at the end | pass |
| E2 | E1 connected | `vadgr model list`, `vadgr model default gemini/<model>` | the catalog lists models; the default is set and the API agrees; **the accepted model id is recorded here for the billed-model table** | CLI output, `curl` body | none | pass |
| E3 | as E2, `ANTHROPIC_API_KEY` in the command's environment only | connect Anthropic as a second, non-default provider, then `vadgr provider logout anthropic` | the connection and its credential record are gone; gemini and its default survive | `curl` body before and after, the credential directory listing before and after | none | pass |
| E4 | E1 connected | `vadgr provider status gemini --refresh` | exit `0`; only gemini's section prints; `catalog_verified_at` read from `GET /api/providers` before and after has advanced | CLI output; both timestamps, filed | none | pass |
| E5 | gemini connected **and default** | `vadgr provider logout gemini` | refuses, non-zero exit; `GET /api/providers` still shows gemini connected and default; the wire behind it answers `409` on `DELETE /api/providers/gemini/connection`, its error code recorded as returned | CLI output and exit code; the `curl` status, code and body | none | pass |
| E6 | E1 connected, stdin not a terminal | `vadgr model default` with no argument | prints the chooser, then refuses with the needs-a-terminal line, non-zero exit; the default unchanged through the API | CLI output and exit code; the `curl` body | none | pass |

## Part F: runs and the watcher

Computer use enabled (`CU3`), gemini connected and default (`E1`, `E2`). Every
claimed success in this part carries its journal line: the journal at the state
root's `runs/<id>/trajectory.jsonl`, written by the loop itself, with `in_flight`
and `done` lines per tool call and a `response` line carrying real `usage`.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| F1 | provider connected and default | `vadgr run "Take one screenshot, then reply done." --background` | exit `0`, the id printed; the run reaches `completed`; **the journal exists at that id with a screenshot tool's `in_flight` and `done` lines and a `response` line carrying `usage`** | CLI output; the run row from the API; the journal's phase counts | none | pass |
| F2 | as F1; a fresh nonce in the task text | `vadgr run "Use your shell tool to run: echo vadgr-e2e-<nonce>. Then stop."` watched | `Run completed`, the results link, exit `0`; the journal is under the **state root's** `runs/`; **the nonce appears in exactly one `done` line** - the countable side effect | CLI output; the journal path and the nonce count | none | pass |
| F3 | a run started and watched as F2 | from another terminal: `vadgr runs cancel <id>` - **the CLI, not a raw HTTP call** | cancel exits `0` and prints the row; the watcher says the run was cancelled and exits `0`; the row reads `cancelled` | both CLI outputs and exit codes; the run row | none | pass |
| F4 | as F1 | `vadgr run "<task>" --background --json` | stdout parses whole, with no hint on it; the row says `queued` | the output through a strict parser | none | pass |
| F5 | as F1; the default model's id known from E2 | `vadgr run "<task>" --provider gemini --model <that id> --json` watched | the first stdout block parses as the run row naming that provider and model; the watch ends `Run completed`, exit `0`; the API row's `provider` and `model` equal the flags | CLI output; the parsed block; the API row | none | pass |
| F6 | as F1 | `vadgr run "Reply with one word." --provider gemini --model vadgr-e2e-no-such-model` watched | the daemon accepts the run (creation does not read the catalog); the first provider call fails; the watcher reports the failure and **exits `1`**; the row reads **`failed`**; the journal carries an `error` line | CLI output and exit code; the row; the journal's error line | F7 consumes this run | pass |
| F7 | F6's run, status `failed` | `vadgr runs resume <id>` - **the CLI, positive path** | resume is accepted and prints the row; the row passes through `running`; **the journal grows past its former last line** and its resumed segment carries the recovered context; it fails again on the same missing model, and the journal then holds **exactly two** error lines - one per attempt, the count that proves the resume really ran | both CLI outputs; the journal's line count before and after, and the two error lines | none | pass |
| F8 | a run started and watched as F2, mid-flight | send SIGINT to the watching CLI | the watcher prints "Detached. The run continues." and **exits `130`**; the run was **not** cancelled: the API row later reads `completed` | the watcher's output and exit code; the row after | none | pass |
| F9 | F1-F8 have left `completed`, `failed` and `cancelled` rows | `vadgr runs list --status failed`, and `curl "$API/api/runs?status=failed"` | both list exactly the failed runs and no other, and equal each other; repeat for `--status completed` and compare counts | both outputs, side by side | none | pass |

## Part R: interruption and recovery

The recovery half of the engine: what a hard kill leaves, what the next boot
does with it, and what the parked state is. `R2` is the resume-success proof: a
side effect that appears **exactly once** across an interruption is what
"recovered, not replayed" means.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| R1 | a watched run mid-flight, on a task shaped "call your time tool's sleep for 30 seconds, then run: echo vadgr-e2e-<nonce>, then stop" (the released runtime's `time` tool ships `sleep`, capped at 60 seconds); the kill lands during the wait | `kill -9` the daemon pid | the watcher prints "The run stream closed. The run continues in the background." and exits `0` - the deliberate no-verdict outcome, observed on purpose; the run row in the database file still reads an active status, read with `sqlite3` directly, since no daemon is alive to ask | the watcher output and exit code; the row read from the file | R2 | pass |
| R2 | R1's state root, daemon dead, one active run in it | start the daemon | the log carries the recovery scan line with `resumed=1`; the run reaches a terminal state; **the journal grew past its pre-kill end**, the resumed segment is marked as such, and **the nonce appears in exactly one `done` line across the whole journal** - interrupted plus recovered is still once | the recovery log line; the journal's pre-kill and final line counts; the nonce count | stop | pass |
| R3 | provider connected and default | `vadgr run "Use your ask_user tool to ask the owner whether to continue, and wait for the answer." --background`, then watch it from a second terminal | the row reaches **`awaiting_approval`**; the watcher prints the waiting-for-approval line; the socket carries an `awaiting` frame. **Disposition, stated rather than silent**: this release ships no reply surface for a parked run - the engine's own source says so at `src/engine/control/hitl.rs` - so the shipped exits are cancel and boot re-park, and this cell proves the park is reachable, visible on every surface, and safe. The reply surface belongs to the release that ships the conversation surface | the row; the watcher line; the captured `awaiting` frame | R4 consumes this run | pass |
| R4 | R3's run parked | restart the daemon, then `vadgr runs cancel <id>` | the recovery scan line says `parked=1` and the row still reads `awaiting_approval` after boot; the cancel then lands: the row reads `cancelled`, and **the daemon stays healthy** - health answers `200` and the log holds no panic | the recovery log line; the row before and after the cancel; health; a grep of the log for panics | stop | pass |

## Part G: pairing and devices

`G2`-`G8` run on the tailscale transport. `G4`'s device token is used again by
`G8` and `W4`; it is a credential and is redacted everywhere outside the
command's own environment.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| G1 | no provider connected | `vadgr pair` | refuses before minting: non-zero exit, the connect-a-provider line printed; **the oracle that can actually see a mint**: the daemon's request log holds **zero `POST /api/auth/pair` lines** for the cell's window - `GET /api/devices` cannot answer this, because a minted code never appears there | CLI output and exit code; the request-log grep and its zero count | none | pass |
| G2 | provider default, tailscale transport | `vadgr pair` | a QR, the machine, the address and the code | CLI output | the code is consumed by G4 | pass |
| G3 | G2's output | decode the printed symbol with `harness/qr-decode` | it recovers exactly the link rebuilt from the printed fields | the decode output | none | pass |
| G4 | G2's live code | `POST /api/auth/claim` from the tailnet address, body `{"pairing_token": "<code>", "device_name": "e2e-probe"}` | `200`; a device token returned exactly once; the device row appears in `GET /api/devices` | the status and body **with the token redacted**; the device row | G8 revokes the device | pass |
| G5 | G4 done: the code is spent | the same claim again | `401` `PAIRING_CODE_INVALID`: one-time means one time | the status, code and body, as returned | none | pass |
| G6 | **its own daemon, with no other pairing traffic**: a wrong-code cell running beside it burns the attempt counter and the code then answers as burned rather than as expired. A freshly minted code, then 301 seconds of wall clock | claim it | `410` `PAIRING_CODE_EXPIRED`: expiry is its own answer, distinct from a wrong code, so the phone says ask for a new one rather than you typed it wrong | the mint time, the claim time, the status, code and body, as returned | none | pass |
| G7 | a freshly minted code | wrong-code claims until the cap answers | within five attempts, `429` `RATE_LIMITED`; the true code is then dead too, per the cap's own message - record what it answers | each attempt's status and code; the final claim of the true code | none | pass |
| G8 | G4's device token; a live run streaming | open `/api/runs/<id>/stream?token=<token>` from the tailnet with `harness/sockets.py --host $(tailscale ip -4) --token <token> --route phone` and see frames flow, then from loopback `DELETE /api/devices/<device-id>` | the tokened socket is admitted and carries frames - the positive token gate; the revoke answers `200` `{"status": "revoked"}`; **the open socket drops now**, not at the next request; the next tokened HTTP request fails the gate; the row is gone from `GET /api/devices`; a second revoke answers `404` `DEVICE_NOT_FOUND` | the frame capture and its cut-off; both DELETE responses; the device list after | none | pass |

## Part W: the sockets, on the wire

The CLI watcher is one consumer of `/api/ws/runs/{id}` and proves nothing about
the wire itself or about the phone's route. Every capture here is made by
`harness/sockets.py`, which speaks the protocol with the standard library alone:
an implementation independent of the server's, and nothing to install on any of
the four targets. It records the frames, their **type counts**, the close code
and any refusal; the cell reads that record and decides.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| W1 | a live run just started (F2's shape) | `python3 harness/sockets.py frames.json --port $VADGR_PORT --run <id> --route cli --seconds 60` | the upgrade answers `101`; every frame parses as JSON carrying a `type`; the terminal frame is present; **the frame type counts are recorded** | `frames.json` whole | none | pass |
| W2 | the same or a fresh live run | the same command with `--route phone` | every frame's `type` is one the published frame vocabulary names - a frame the phone has no case for is a **fail**, not a curiosity; the terminal frame is present; the type counts are recorded | `frames.json` whole; the vocabulary check's output | none | pass |
| W3 | daemon on loopback | the same command with `--run run-does-not-exist` and no `--route`, so both are driven | the upgrade is accepted and the socket closes at once with **close code `4004`** on both routes, zero frames | the record for both routes | none | pass |
| W4 | tailscale transport; a live run; G4's token known | the same command with `--host $(tailscale ip -4) --token WRONG`, then again with no `--token` at all | both routes close **`4401`** in both attempts, because a non-loopback source is never admitted without a valid token; the same connect with G4's token is admitted (proven in `G8`) | both records | none | pass |

## Part S: what only loopback may do

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| S1 | tailscale transport; a provider connected | call two guarded verbs from the tailnet address, then the same call on loopback | the tailnet call is refused and the loopback call succeeds, so the route exists and the refusal is the gate. **The token gate runs first**: an untokened tailnet call answers `401` `MISSING_TOKEN` and never reaches the source check, so `403` `SOURCE_NOT_AUTHORIZED` needs a valid device token presented from a non-loopback address, which means a paired handset. Record which of the two the wire returned rather than assuming the order | both statuses and error codes as returned, and the loopback status | none | pass |

## Part O: OAuth and the callback listener

The callback listener is its own served surface on `127.0.0.1:1455`. `O1` and `O2` need no account. `O3` and `O4` were written while the account was
not available and were marked `blocked` by name rather than deleted. The owner
supplied both during this pass, so they ran: the key from the machine's
environment for `O4`, and a live browser sign-in for `O3`.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| O1 | daemon running; the log line "OpenAI callback listening" present | `curl -i` against `127.0.0.1:1455`: `/auth/complete`, `/auth/failed`, and `/auth/callback?state=bogus&code=bogus` | `/auth/complete` answers `200` with the connected page; `/auth/failed` answers `400` with the failed page; the bogus callback redirects to `/auth/failed`; **the daemon log records the callback's method and path only - the query string appears nowhere in the log**, which is the credential-redaction property this listener exists to keep | the three responses; the log lines; a grep of the whole log for the bogus values returning zero | none | pass |
| O2 | a plain listener bound on `1455` **before** the daemon starts | start the daemon, run `vadgr provider login openai --auth chatgpt`, then one direct `POST /api/providers/openai/auth-attempts` with method `oauth` to record the wire's own answer, then release the port | the daemon logs the callback port unavailable; the login is refused and the CLI says the callback is unavailable; the direct call answers `503`, its error code recorded as returned; after the port is released the daemon binds within its retry and logs "OpenAI callback listening" | the log lines either side; the CLI output and exit code; the wire status and code | stop | pass |
| O3 | the owner's OpenAI account, supplied during this pass | `vadgr provider login openai --auth chatgpt`, the browser authorization completing against `127.0.0.1:1455/auth/callback` | the attempt is minted (`POST /api/providers/openai/auth-attempts`, method `oauth`); `GET /api/provider-auth/<id>` reaches its ready state; the connection commits (`PUT /api/providers/openai/connection`); the provider reads connected with `auth_method` `oauth`; **no token value appears in the log, the database greps or this evidence** | CLI output; the attempt's states as polled; the provider row; the zero-count greps | the connection is removed | pass |
| O4 | `OPENAI_API_KEY` in the command's environment only, supplied during this pass | `vadgr provider login openai --auth api-key`, then `vadgr provider logout openai` | connected via `api_key` with a live catalog, then cleanly disconnected; the key absent from disk and evidence, as in `E1` | CLI output; provider row before and after; the zero-count greps | none | pass |

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
| H1 | `H2` done, so the handset is paired; Tailscale still on | **tester**: open the app, then open the machine's row | the app names the machine by the hostname the operator states and shows it healthy; on the daemon side the device row's **`last_seen` advances past its `paired_at`**, which only a request carrying the device token does, and the request log holds `GET /api/runs` calls the operator never made. **The request log records no source address** (finding F5), so it cannot say a request came from the tailnet; `last_seen` is the read that can | the device row before and after, the request counts by route | none | pass |
| H2 | Tailscale on and connected on the phone; the app open; this machine not already paired; the operator has just run `vadgr pair` and can see the QR | **tester**: tap Add machine, scan the QR the operator is showing, or type the code exactly as printed including the hyphen | `POST /api/auth/claim` answers `200` in the request log and a device row appears in `GET /api/devices`; the app shows the machine by name | the log line, the device row, the app's machine list | the device stays for `H1`-`H4`; `H5` unpairs it from the handset | pass |
| H3 | `H1` done; a provider connected and a default model set; the tester has the machine's conversation open | **operator**: start the run on the machine with `vadgr run "Take one screenshot and tell me in five words what you see" --background`, and say the run id aloud. **tester**: pull the conversation down to refresh until the run's line appears, then stop pulling and watch the line until it finishes | the run's line appears **on a pull**, never on its own: the released list is a one-shot read behind a pull gesture, and a run arriving unpulled ships with `vadgr-mobile 0.5.0`'s machine stream, so unprompted arrival here is a **fail**, not a bonus. Once present, the live line renders progress **without further pulls** and settles on the same terminal status `GET /api/runs/<id>` serves; the daemon's log holds the handset's `GET /api/runs/<id>/stream` from the tailnet address, which is the phone's socket and the one no other cell drives from a handset | the daemon's stream log line with its source address, the run row over time, the journal under the state root's `runs/<id>/` | none | pass |
| H4 | `H3` finished | **tester**: tap the run's line so its sheet opens, and read out the status and the text under "WHAT IT PRODUCED" | the status the sheet shows equals the status `GET /api/runs/<id>` serves at the same moment, and the produced text matches the run's stored `outputs.result`; the daemon's log holds the handset's read of that run | the tester's spoken status and the API body, captured together with the time; the log line | `H5` unpairs from the handset | pass |
| H5 | `H4` done; the handset still paired | **tester**: open the machine, choose Unpair, and confirm the dialog that says the phone forgets the machine and its access is revoked | `DELETE /api/devices/<device_id>` arrives in the daemon's request log **from the handset's tailnet address**; the device row is gone from `GET /api/devices`; the app returns to its unpaired state, and any further read from the phone is refused by the token gate | the DELETE log line with its source address; the device list after; the refused read in the log | none: the unpair is the cleanup | pass |

## Part I: the installer, the update, on a machine that does not have the product

`vadgr update` follows the released default branch by design, so `I4`-`I6`
exercise the command against that branch, driven by binaries built at the head
under test. That is the command's real shape, stated rather than hidden.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| I1 | a container with a shell, git and curl, **no toolchain and no vadgr** | assert both absences | `cargo` and `vadgr` are not found | the two failed lookups | the container is removed | pass |
| I2 | as I1 | run `install.sh` against the commit under test | it installs the toolchain, builds, and puts both binaries in the install root; **`git rev-parse HEAD` inside the container equals the PR head recorded in `A1`** - the invalidated pass drifted here | the transcript, the install root listing, both head hashes side by side | as I1 | pass |
| I3 | as I2 | `vadgr --version`, then `vadgr health` | the version matches; health exits `3` because nothing is started, which is the correct answer | CLI output and both exit codes | as I1 | pass |
| I4 | as I3; the clone at a head not behind the released default branch | `vadgr update --check` | exit `0` with "vadgr is up to date." | CLI output and exit code | as I1 | pass |
| I5 | as I4, then `git -C ~/.vadgr/src reset --hard origin/master~2` | `vadgr update --check` | exit `0`; "2 commit(s) available"; the Cargo.lock line printed **when and only when** the range touches `Cargo.lock` - record which it was | CLI output; `git log --oneline` of the range; whether the range touches `Cargo.lock` | as I1 | pass |
| I6 | `I5` done, the checkout two commits behind | `vadgr update` | it pulls fast forward only, rebuilds and reinstalls; the installed checkout's HEAD equals the origin's; **the binary hash changes when the pulled commits changed Rust source, and legitimately does not when they did not**, so record which kind of commits were pulled beside the hashes | the checkout's HEAD before and after, both binary hashes, and what the pulled commits touched | the container is removed | pass |

## Part J: state lives where the platform says

The release's first sentence, exercised without the override every other cell
uses. **The guard comes first and is absolute**: if the platform root already
holds anything, the cell is `blocked` by name and nothing there is touched - a
real installation is never the fixture.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| J1 | the platform state root absent or empty, checked and filed first: Linux and WSL `${XDG_STATE_HOME:-$HOME/.local/state}/vadgr`, macOS `~/Library/Application Support/vadgr/state`, Windows `%LOCALAPPDATA%\vadgr` | `env -u VADGR_STATE_HOME vadgr start` on a fresh port, then `env -u VADGR_STATE_HOME vadgr stop` | the daemon serves; `vadgr.db` and `credentials/` appear **under the platform root above**, and nothing appears under the working directory | the guard listing; the platform-root listing while serving; health; the working-directory listing | remove exactly the files the boundary listed, then show the root empty again | pass |

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
| automated gate | pass | not run | not run | not run | |
| surface sweep | pass | not run | not run | not run | |
| A: the built head | pass | not run | not run | not run | |
| B: the consolidation | pass | not run | not run | not run | |
| C: the service group | pass | not run | not run | not run | |
| D: read-only commands | pass | not run | not run | not run | |
| CU: computer use | pass | not run | not run | not run | |
| E: provider onboarding | pass | not run | not run | not run | |
| F: runs and the watcher | pass | not run | not run | not run | |
| R: interruption and recovery | pass | not run | not run | not run | |
| G: pairing and devices | pass | not run | not run | not run | |
| W: the sockets | pass | not run | not run | not run | |
| S: source enforcement | pass | not run | not run | not run | the token gate answers before the source gate; see the cell |
| O: OAuth and the callback | pass | not run | not run | not run | the owner supplied the account and the key during this pass |
| H: the phone | pass | not run | not run | not run | a person held the handset: pair, machine, run, read back, unpair |
| I: the installer and update | pass | not run | not run | not run | in a container with no toolchain and no product |
| J: the platform state root | pass | not run | not run | not run | no overrides at all, state under the platform root |
| **overall** | pass | not run | not run | not run | the weakest part actually driven on this OS, which is every part |

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

### F6 (open): health says a disabled module is available

`vadgr computer-use disable` sets `enabled` to `false` on
`GET /api/settings/computer-use`, and `GET /api/health` goes on reporting
`"computer_use": true`. The two answer different questions and only one of them
is on the health surface: health reads whether the runtime is installed
(`src/routes/health.rs`), while the loop reads whether it is enabled before
mounting the tools (`src/engine/mcp/mod.rs`). With the setting off, a run gets
no computer-use tools and health still calls the module available, so the one
screen a user checks after turning something off tells them nothing turned off.

Found by `CU2`. Open: the fix is daemon code, and rebuilding the daemon
mid-pass would invalidate every daemon-side cell already run against this
build. It is small and belongs in the next release that touches health.

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

## Surface coverage - **every published endpoint, with what it returned**


### Shipped

| endpoint | what was asked | status | code | response, as returned |
|---|---|---|---|---|
| `GET /api/health` | the daemon is up | `200` | - | `{"modules":{"computer_use":true},"platform":"wsl","status":"healthy","transport":{"advertise_host":null,"available":true,"bind_host":"127.0.0.1","name":"loopback"},"version":"0.4.9"}` |
| `GET /api/providers` | the provider list | `200` | - | `[{"auth_method":null,"auth_methods":["oauth","api_key"],"available":false,"catalog_stale":false,"catalog_verified_at":null,"connected":false,"default_model":null,"id":"openai","is_default":false,"kind` |
| `GET /api/settings/computer-use` | the computer-use setting | `200` | - | `{"daemon":null,"enabled":true,"platform":"wsl2","venv_ready":true}` |
| `GET /api/computer-use/status` | the runtime's own status | `200` | - | `{"available":true,"platform":"wsl2"}` |
| `GET /api/devices` | paired devices | `200` | - | `[]` |
| `GET /api/runs` | the run list | `200` | - | `[{"agent_name":"Take one screenshot.","completed_at":"2026-08-19T18:47:43.008773+00:00","id":"run-d347ef4421da4225a5d5bb3b3b2112c0","inputs":{"task":"Take one screenshot."},"log_path":null,"model":"ge` |
| `GET /api/runs/run-d347ef4421da4225a5d5bb3b3b2112c0` | one run | `200` | - | `{"agent_name":"Take one screenshot.","completed_at":"2026-08-19T18:47:43.008773+00:00","id":"run-d347ef4421da4225a5d5bb3b3b2112c0","inputs":{"task":"Take one screenshot."},"log_path":null,"model":"gem` |
| `POST /api/runs/run-d347ef4421da4225a5d5bb3b3b2112c0/cancel` | negative: cancelling a finished run | `409` | `RUN_NOT_ACTIVE` | `{"error":{"code":"RUN_NOT_ACTIVE","details":{},"message":"Run is already finished"}}` |
| `POST /api/runs/run-d347ef4421da4225a5d5bb3b3b2112c0/resume` | resume | `409` | `RUN_NOT_RESUMABLE` | `{"error":{"code":"RUN_NOT_RESUMABLE","details":{},"message":"Only failed runs can be resumed (current status: completed)"}}` |
| `GET /api/runs/run-does-not-exist` | negative: no such run | `404` | `RUN_NOT_FOUND` | `{"error":{"code":"RUN_NOT_FOUND","details":{},"message":"Run with id 'run-does-not-exist' not found"}}` |
| `POST /api/runs` | negative: no task | `422` | - | `{"detail":[{"msg":"Failed to deserialize the JSON body into the target type: missing field `task` at line 1 column 2","type":"value_error"}]}` |
| `POST /api/auth/pair` | mint a pairing code | `503` | `TRANSPORT_UNREACHABLE` | `{"error":{"code":"TRANSPORT_UNREACHABLE","details":{"transport":"loopback"},"message":"Transport cannot advertise a reachable address. Enable Tailscale (VADGR_TRANSPORT=tailscale) to pair over your ta` |
| `POST /api/auth/claim` | negative: a code that was never minted | `401` | `PAIRING_CODE_INVALID` | `{"error":{"code":"PAIRING_CODE_INVALID","details":{},"message":"That pairing code is wrong or has already been used."}}` |
| `POST /api/providers/gemini/catalog-refresh` | refresh a connected catalog | `200` | - | `{"auth_method":"api_key","auth_methods":["api_key"],"available":true,"catalog_stale":false,"catalog_verified_at":"2026-08-19T18:58:20.796890+00:00","connected":true,"default_model":"gemini-2.5-flash",` |
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
| `vadgr runs list` | `0` | stdout | `Run ID    Task                                                          Status     Duration` |
| `vadgr runs` | `0` | stdout | `Run ID    Task                                                          Status     Duration` |
| `vadgr runs get run-d347` | `0` | stdout | `Run ID:       run-d347ef4421da4225a5d5bb3b3b2112c0` |
| `vadgr runs cancel run-d347` | `1` | stderr | `Error: Run is already finished` |
| `vadgr runs resume run-d347` | `1` | stderr | `Error: Only failed runs can be resumed (current status: completed)` |
| `vadgr runs get zzzzzzzz` | `1` | stderr | `Error: No run matching 'zzzzzzzz' found.` |
| `vadgr provider status` | `0` | stdout | `OpenAI: not connected` |
| `vadgr model list` | `0` | stdout | `Google Gemini: connected (default)` |
| `vadgr status` | `0` | stdout | `Service  PID   Status ` |
| `vadgr logs --no-follow -n 2` | `0` | stdout | `2026-08-19T18:58:21.311322Z  INFO request{method=GET uri=/api/health version=HTTP/1.1}: tower_http::trace::on_response: finished processing request latency=0 ms status=200` |
| `vadgr update --check` | `1` | stderr | `Error: /tmp/vadgr-049-e2e-final/c/vhome/src is not a git checkout, so it cannot be updated. Reinstall with the installer instead.` |
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
  cli: {'agent_completed': 1, 'agent_log': 1, 'agent_started': 1, 'run_completed': 1, 'run_started': 1}  -> identical across the three
  phone: {'completed': 1, 'output': 2, 'started': 1, 'tool_call': 1}  -> identical across the three

=== turn-0 input tokens, with the model now pinned in all three
  8821: model gemini-2.5-flash, turn-0 input 1774, output 12
  8822: model gemini-2.5-flash, turn-0 input 1774, output 12
  8823: model gemini-2.5-flash, turn-0 input 1774, output 12

  identical output counts on turn 0 are expected here and are not one
  result reused: turn 0 is a tool call with no text, so its size is the
  same shape every time. The three passes are three real calls, and the
  final turns say so:
    8821: run run-dae474be8b40  usage {'input_tokens': 3834, 'output_tokens': 18}  result 'I have taken a screenshot.'
    8822: run run-ada7f67f6161  usage {'input_tokens': 3834, 'output_tokens': 18}  result 'I have taken a screenshot.'
    8823: run run-18620276396a  usage {'input_tokens': 3834, 'output_tokens': 33}  result 'I have taken a screenshot. Is there anything specific you would like me to do with it or observe?'
```

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

# 0.4.8 - the CLI is Rust, and the product answers to one set of names: e2e runbook

The `vadgr` command a person types is a Rust binary, with the same verbs, the
same arguments and the same exit codes it had in Python, and it drives both
daemons over their public surfaces. The environment variables are one family now
rather than two, and the run watcher no longer goes silent when a run is
cancelled.

> **Status: run on all four supported operating systems, and complete on all
> four.** macOS was the last one owed and ran on 2026-08-19 at `00055b3` on
> macOS 26.5.2 build 25F84, arm64: all 45 cells carry a verdict, 44 pass and
> `H4` is the same structural `partial` it is everywhere. The gate is green,
> rust 272, api 445, cli 150, engine 122, with `fmt` and `clippy` at exit `0`.
> **The rust count is not the same number on every host and should not be**:
> this pass added two tests with its fix, and macOS additionally compiles three
> `tailscale.rs` tests gated to it, so the honest figures are 269 on Linux and
> WSL and 272 on macOS from the same tree. An earlier version of this line said
> the pass added five tests and that the gate matched every host exactly; native
> Linux measured 269 at the same commit and the gate rows now carry the figure
> each host actually produced. `G4` paired a real handset over the
> tailnet from a Mac. **It found and fixed one defect, `F15`**: `vadgr start`
> could not survive a busy port, printing `Port 8815 busy, using 8815` before
> the daemon died on bind. `F16` records a macOS rendering observation that is
> not a failure.
>
> **The earlier status: run on WSL2, on native Windows and on native Linux, and complete on
> all three.** Native Linux ran on 2026-08-19 at `bc7921d` on Ubuntu 26.04 with a
> GNOME Wayland session: all 45 cells carry a verdict, 44 pass and `H4` is the
> same structural `partial` it is everywhere. The gate matches WSL exactly here,
> rust 267, api 445, cli 150, engine 122, with `fmt` and `clippy` at exit `0`,
> and native Linux does not carry the eight api failures `F8` records on Windows.
> `G4` paired a real handset over the tailnet. Three findings were added, `F12`
> to `F14`, and two of them are repairs to this runbook's own handoff. **macOS
> remains `not run`.**
>
> **The earlier status: run on WSL2 and on native Windows, 2026-08-18, and complete on both.**
> All 45 cells carry a verdict on each. Automated gate green on WSL (rust 267,
> api 445, cli 150, engine 122); on Windows the api suite is 436 of 445 and the
> eight failures are `F8`, all older than this branch. **Native Linux and macOS
> are `not run`.** Findings are listed below, and four WSL cells were re-run
> after the Windows pass fixed two defects. Nothing is marked pass that was not
> executed and read back.

## How a pass is run, before anything else in this file

The four rules in [`../README.md`](../README.md) hold here without restatement:
whatever needs the owner runs first, the pass does not stop to report, a bug
found is a bug fixed here and now with a test that fails without the fix, and a
fix invalidates the cells it touched on every operating system that had passed
them.

**One command at a time.** Every product command is invoked on its own and its
output and exit code are read before the next command is chosen. No `&&`, no
loop, no driver script that sequences product commands. Helpers may build
isolated state before a group and parse evidence after a command has run.

## The approach

This minor's subject is a **command-line surface**, so the driver is the
installed `vadgr` binary invoked in a terminal, one command at a time, exactly as
a person invokes it. The oracles are outside the CLI: the daemon's own HTTP
responses read with `curl`, the run journal, the process table, the pid and port
files on disk, and for the QR a decode of the payload rather than a look at the
picture.

**Both daemons are driven, because at this release both exist and the CLI must
work against the one in front of it.** `vadgr start` launches the **Python**
daemon, which is the strangler seam this release must not break. Provider
onboarding, `model default` and the pairing routes are the **Rust** daemon's, so
the groups that use them run against it. Each group names which daemon it drove.

## Owner and environment requirements

| requirement | cells | non-secret availability check | cost or destructive effect | cleanup |
|---|---|---|---|---|
| a Gemini API key in `../.env` | `E1`-`E6`, `G1` | the file carries a Gemini key under `GEMINI_API_KEY` or a machine-local alias; the driver maps the alias to the portable name **in that command's environment only** and never prints the value | one authenticated catalog call and one bounded readiness call | the isolated state root is removed |
| A handset with the Vadgr app, held by the owner | `G4` | the owner confirms the phone is in hand | none | none |
| A Python virtual environment at `api/.venv` | `C1`-`C8` | `test -x api/.venv/bin/python` | none | none |
| the host under test, with a free loopback port range `8810`-`8830` | all | nothing is bound on them: `ss -ltn` on Linux or WSL, `netstat -an -p tcp` on macOS, `Get-NetTCPConnection -State Listen` on Windows | none | every daemon started is stopped by its own pid |

**`G4` is the only cell that needs a person**, and the owner is told before the
`G` group runs. Every other cell runs unattended.

## Billed model selection

| cells | provider/auth | required capabilities | selected model | official source and date | input/output price | hard iterations/tokens/cost | escalation condition |
|---|---|---|---|---|---|---|---|
| `E1`-`E6`, `F1`-`F4` | Gemini / API key | text generation, tool calls, authenticated catalog | `gemini-3.5-flash-lite` | the authenticated catalog read in `E4` on 2026-08-18 | read from the catalog; the cheapest listed text model | 10 iterations, 60,000 input tokens, USD 0.05 | none: a capability failure ends the group rather than escalating |

## Prerequisites

```bash
export E2E_HOME=/tmp/vadgr-048-e2e          # the installer-shaped home
export E2E_ROOT=$E2E_HOME/state             # isolated state, database and runs
export PATH="$E2E_HOME/bin:$PATH"           # the tested installation, first
export VADGR_HOME=$E2E_ROOT/home            # pid files, port files, api.log
export VADGR_DB=$E2E_ROOT/vadgr.db
export VADGR_RUNS_DIR=$E2E_ROOT/runs
export VADGR_STATE_HOME=$E2E_ROOT/state-home
export VADGR_PORT=8811
export VADGR_TRANSPORT=loopback
command -v vadgr                            # must resolve inside $E2E_HOME
sha256sum "$(command -v vadgr)"             # shasum -a 256 on macOS; must match the PR head's build
```

The `vadgr` and `vadgr-daemon` binaries are built from the PR head with
`cargo build --release --bins` and copied into `$E2E_HOME/bin`. That is the same
shape the Rust daemon has been driven in since `0.4.5`: the installer still puts
the Python CLI on a user's `PATH`, and both halves swap at the `0.4.9` cutover.

## Remote-host handoff for Linux, macOS and Windows

Each native-host session follows this without context from another session.
**Every prerequisite below was learned by running the pass**, so a host that
cannot meet one knows before it starts rather than four groups in.

1. **Read first**: `AGENTS.md`, `E2E/README.md` and this runbook, whole. Check
   out the same PR head, record `git rev-parse HEAD`, and put it in every result
   you write. **Do not combine results from different commits**: three defects
   were fixed during the WSL pass and every cell observed against a superseded
   build was re-run.

2. **Build and install the product, never run it from the source tree.**

   ```bash
   cargo build --release --bins
   mkdir -p "$E2E_HOME/bin"
   cp target/release/vadgr-cli  "$E2E_HOME/bin/vadgr"          # vadgr-cli.exe on Windows
   cp target/release/vadgr-daemon "$E2E_HOME/bin/vadgr-daemon"
   ```

   Put `$E2E_HOME/bin` **first** on `PATH`. `A1` records `command -v vadgr` and
   the `sha256` of what it resolves to, and that hash must be the release build
   of the head you checked out. `cargo run` is not an invocation of the product.

3. **`vadgr-computer-use` is not needed by this runbook**, and that is not an
   omission. Nothing here drives a desktop: `computer-use status` reads a
   setting, and the `F` group runs tasks that use the control tools only. Leave
   cua uninstalled and expect `modules.computer_use` to be `false`.

4. **Two prerequisites decide which groups you can run**, and neither is
   negotiable by trying harder:

   - **Part C needs the still-shipped daemon's virtual environment** at
     `api/.venv`, because `vadgr start` launches it. Create it from
     `api/requirements.txt` before `C1`. Without it `C1` fails with
     `API venv not found`, which is the CLI reporting correctly rather than a
     defect, and `C1`-`C8` plus `B4` are `blocked` with that reason.
   - **`G2` and `G3` need a transport that advertises an address.** On
     `loopback` the daemon has no advertise host, so `POST /api/auth/pair`
     refuses rather than handing out a QR no phone could use. Run those two cells
     with `VADGR_TRANSPORT=tailscale` on a host where `tailscale status` reports
     a logged-in node. Without one, `G1` still runs and `G2`-`G4` are `blocked`
     naming the missing transport.

5. **The isolated environment.** Use a free port per concurrent pass. Nothing
   here touches the owner's normal installation.

   ```bash
   export E2E_HOME=/tmp/vadgr-048-e2e            # or an empty host-local root
   export E2E_ROOT="$E2E_HOME/state"
   export PATH="$E2E_HOME/bin:$PATH"
   export VADGR_HOME="$E2E_ROOT/home"            # pid files, port files, api.log
   export VADGR_DB="$E2E_ROOT/vadgr.db"
   export VADGR_RUNS_DIR="$E2E_ROOT/runs"
   export VADGR_STATE_HOME="$E2E_ROOT/state-home"
   export VADGR_REPO="$(git rev-parse --show-toplevel)"   # Part C only
   export VADGR_PORT=8811
   export VADGR_TRANSPORT=loopback               # tailscale for G2 and G3
   ```

   ```powershell
   $env:E2E_HOME = "$env:TEMP\vadgr-048-e2e"
   $env:E2E_ROOT = "$env:E2E_HOME\state"
   $env:PATH     = "$env:E2E_HOME\bin;$env:PATH"
   $env:VADGR_HOME        = "$env:E2E_ROOT\home"
   $env:VADGR_DB          = "$env:E2E_ROOT\vadgr.db"
   $env:VADGR_RUNS_DIR    = "$env:E2E_ROOT\runs"
   $env:VADGR_STATE_HOME  = "$env:E2E_ROOT\state-home"
   $env:VADGR_REPO        = (git rev-parse --show-toplevel)
   $env:VADGR_PORT        = "8811"
   $env:VADGR_TRANSPORT   = "loopback"
   ```

6. **The order, and what carries between cells.** `A` needs nothing running.
   Start the Rust daemon directly for `B1`-`B3`, `B6`, `D`, `E`, `F`, `G` and
   `H3`-`H5`. Run `C` next, because `C7` and `C8` leave the port file that `B4`
   reads and `B5` needs no daemon at all. `E` before `F` and `G`, because a run
   needs a connected provider and pairing needs a default one. **Run `E6a`
   before `E6b`**: logging out the default is refused, which is the cell, and the
   successful logout needs a second provider connected first.

   The task in the `F` group must **take an action**. This engine fails a turn
   that only replies, with `NO_ACTION_TAKEN`, so use the task the WSL pass used:
   `Use your todo tool to write a two step plan for ..., mark both steps
   completed, then finish.`

7. **Evidence, before cleanup.** Create the boundary directory before the first
   cell and file each group's output at its boundary. Record the host, both
   artifact hashes and the head in a `host.txt`. Run `harness/sweep.py` once the
   cells are done, then `harness/tables.py` to generate the coverage tables:
   **the tables are generated from the record, never typed.** `harness/README.md`
   explains all four helpers.

8. **Cleanup.** Stop only the daemons you started, **by pid**, and check for
   strays afterwards. A blanket kill takes down another pass. Remove only the
   isolated root. Do not stop unrelated processes.

9. **Credentials.** Read only what a cell needs from the owner-only `../.env`,
   into that command's environment only. Never echo a value, and never put one in
   an argument, a log or an evidence file. Run
   `python3 scripts/check_no_secrets.py --env-file ../.env` before the group and
   again before the evidence is sealed, and grep the sealed boundary for each key
   you used. The `E` group needs `GEMINI_API_KEY` and `ANTHROPIC_API_KEY`.

10. **Write your own results into the per-OS table and the cell status column**,
    from observation. A cell you did not run is `not run` with a reason, never a
    blank and never inherited from another host.

## Automated gate (necessary, never sufficient)

- `cargo test` in `rust/` -> **269 passed** on WSL, 1 ignored (Docker only). macOS reports 272; the difference is the tests each platform compiles
- `python3 -m pytest api/tests/ -q` -> **445 passed** on WSL. On native Windows 436 of 445 pass and the 8 failures are `F8`, every one of them older than this branch
- `PYTHONPATH=. python3 -m pytest cli/tests/ -q` -> **150 passed**
- `PYTHONPATH=. python3 -m pytest engine/tests/ -q` -> **122 passed**
- `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings` -> exit `0`

The suites know nothing about whether the CLI reaches a daemon, whether a table
has rows in it, whether a cancelled run says so on a real socket, or whether the
QR on the screen encodes the link the phone needs. That is this runbook's half.

## Coverage

| Part | Axes | Cells | Run | Open |
|---|---|---|---|---|
| A identity | binary x head x tree | 3 | 3 | 0 |
| B address resolution and the rename | source x precedence x staleness | 6 | 6 | 0 |
| C the service group, Python daemon | verb x state | 8 | 8 | 0 |
| D read-only commands, Rust daemon | command x populated state | 6 | 6 | 0 |
| E provider onboarding, Rust daemon | verb x live credential | 7 | 7 | 0 |
| F runs and the watcher, Rust daemon | outcome x flag | 6 | 6 | 0 |
| G pair and the QR, Rust daemon | render x decode x handset | 4 | 3 | 1 |
| H negatives and exit codes | failure class | 5 | 5 | 0 |
| | | **45** | **45** | **0** |

## Part A: the thing under test is the thing that was built

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| A1 | `$E2E_HOME/bin` first on `PATH` | `command -v vadgr` | resolves inside `$E2E_HOME/bin`, never to a system or Python `vadgr` | the resolved path and its `sha256` | none | **pass** on `e3799b1`: `command -v vadgr` resolved to `/tmp/vadgr-048-e2e/bin/vadgr`, whose `sha256` matches the release build of the head under test. |
| A2 | as A1 | `vadgr --version` | prints `vadgr 0.4.8`, matching the crate manifest and `api/config.py` | the printed line | none | **pass**: `vadgr 0.4.8`, agreeing with `rust/Cargo.toml` and `api/config.py`, which a unit test keeps in step. |
| A3 | as A1 | `vadgr --help` | lists every shipped verb, and names none of `registry`, `agent`, `workflow`, `project`, `forge` | the help text | none | **pass**: all fifteen verbs listed. `registry`, `agent`, `workflow`, `project` and `forge` appear zero times. |

## Part B: one family of names, and an address resolved in the stated order

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| B1 | Rust daemon listening on `8811`; no port file | `VADGR_PORT=8811 vadgr health` | exit `0`, the daemon's own `/api/health` body agrees with the printed fields | CLI output, `curl` read-back | none | **pass on `d1b3f2f`**, re-run after `F7` changed the platform field. Exit `0`, and every printed field equals the `/api/health` body read with `curl`. **The first attempt at this re-run was a harness fault, recorded rather than hidden**: it used the home `C1` had just written a port file into, so the CLI correctly followed that file to the Python daemon while the oracle read the Rust one. The cell's own precondition says no port file, and it passes against a clean home. |
| B2 | daemon on `8811`; `VADGR_PORT` set to a dead port | `VADGR_PORT=8899 VADGR_API_URL=http://127.0.0.1:8811 vadgr health` | exit `0`: the URL wins over the port | CLI output | none | **pass**: exit `0` with `VADGR_PORT` naming a dead port, so the URL wins. |
| B3 | as B2 | `VADGR_API_URL=http://127.0.0.1:8899 vadgr --api-url http://127.0.0.1:8811 health` | exit `0`: the flag wins over the environment | CLI output | none | **pass**: exit `0` with `VADGR_API_URL` naming a dead port, so the flag wins. |
| B4 | a daemon started by `vadgr start` on an auto-incremented port, so the port file names a port the environment does not | `vadgr health` with `VADGR_PORT` still naming the busy original | exit `0` against the port in the file; the pid in `api.pid` is the live daemon | the pid and port files, the listener list | stopped in C6 | **pass**: the daemon had walked up to `8813` after `C8`, and `vadgr health` reached it while `VADGR_PORT` still said `8812`. The port file wins, which is what makes the listing's own port usable. |
| B5 | a port file naming a port whose pid is dead | `vadgr health` | the stale file is removed and the default is used; exit `3` with nothing listening | the directory listing before and after | none | **pass**: a port file naming pid `999999` was ignored, **both files were removed**, and the CLI fell to the default `8000` and exited `3`. |
| B6 | daemon on `8811`; `VADGR_API_URL` unset | `FORGE_API_URL=http://127.0.0.1:8811 AGENT_FORGE_PORT=8811 vadgr health` with `VADGR_PORT` unset | exit `3`: the old names are read by nothing, so the CLI falls to the default port `8000` | CLI output | none | **pass**: with `FORGE_API_URL`, `AGENT_FORGE_PORT` and `FORGE_HOME` all set and the new names unset, the CLI used the default `8000` and exited `3`. Nothing reads the old names. |

## Part C: the service group still drives the Python daemon

Every cell in this part runs against the **Python** daemon, started by the public
`vadgr start`. That is the strangler seam: the Rust CLI supervising the Python
process.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| C1 | isolated `VADGR_HOME`; nothing on the port | `vadgr start` | exit `0`; prints the bind addresses and the real endpoint; `/api/health` answers on that port; the process is `python -m api.serve` | CLI output, `ps` line for the pid, `curl` health | C6 | **pass on `d1b3f2f`**, re-run after `F7`. Exit `0`; the pid file names `api/.venv/bin/python -m api.serve --host 127.0.0.1 --port 8812`, so the Rust CLI started the **Python** daemon. **Its `/api/health` now answers `"platform":"wsl"` where it answered `"wsl2"` before the fix**, which is `F7` observed on this OS: both daemons name the same machine the same way. |
| C2 | C1's daemon running | `vadgr start` | refuses: "already running", non-zero exit, and the running pid is unchanged | CLI output, the pid before and after | C6 | **pass**: refused with `vadgr is already running`, exit `1`, and the pid was unchanged before and after. |
| C3 | as C2 | `vadgr status` | a table with `api`, the live pid, and `running` | CLI output, `ps` | C6 | **pass**: `api 33537 running` plus the `daemon` row, and every line of the table is the same visible width (23). |
| C4 | as C2 | `vadgr logs --no-follow -n 5` | prints the last lines of `$VADGR_HOME/api.log` and exits `0` | CLI output, `tail -5` of the file | C6 | **pass**: the five lines printed are byte-identical to `tail -5` of `api.log`. |
| C5 | as C2 | `vadgr logs` (follow), interrupted after new lines arrive | prints the tail, then the appended lines, then ends on the interrupt without killing the daemon | CLI output, the daemon still answering health afterwards | C6 | **pass**: printed the tail, then the line the daemon wrote for a fresh health request, then ended on the interrupt. The daemon answered health afterwards, so the follower did not take it down. |
| C6 | as C2 | `vadgr stop` | exit `0`; the pid is gone from the process table, the port is free, the pid and port files are removed | CLI output, `ps`, the listener list, directory listing | none | **pass**: exit `0`; the process was gone, `8812` had no listener, and both the pid and port files were removed. |
| C7 | stopped | `vadgr restart` | exit `0`; a **new** pid serves health on the port | CLI output, the two pids | stop | **pass**: exit `0` from a stopped state, saying so first; a new pid (`34221`, previously `33537`) served health on the port. |
| C8 | something already bound to the configured port | `vadgr start` | says the port is busy, walks up to a free one, and the port file names the port it actually took | CLI output, the listener list, the port file | stop, release the squatter | **pass on `0a7fb17`**, re-run after `F15`. A squatter held `127.0.0.1:8812` listening with a backlog of one and never accepting, which is the shape that broke the old search. The CLI printed `Port 8812 busy, using 8813`, started there, the port file names `8813` and health answers on it. **WSL was affected on the merits, not only by the rule**: probing the held port from this host reports `in use`, then `free`, then `free`, which is exactly the disagreement the old connect-based search acted on. | **On macOS this cell failed and found `F15`**: the CLI printed `Port 8815 busy, using 8815`, naming the same port twice, and the daemon died on bind. Re-run against the fix in `00055b3` it prints `Port 8815 busy, using 8816`, the port file names 8816 and health answers there. The earlier passes observed the old search, so this cell is owed again on WSL, native Linux and native Windows. **Native Linux re-ran it at `d80c692`**: `Port 8812 busy, using 8813`, two different ports named, the port file reads `8813`, health answers there and the listener on `8813` is the pid the file names. `C1` to `C7` and `B4` were re-run with it rather than only `C8`, because `find_free_port` is called by every `vadgr start` and `B4` reads the port file `C8` writes; all nine pass.

## Part D: the read-only commands, against the Rust daemon

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| D1 | Rust daemon on `8811`, fresh database | `vadgr health` | `Status`, `Version`, `Platform` and a `Modules:` block; every value equals the `/api/health` body | CLI output, `curl` body | none | **pass on `d1b3f2f`**, re-run after `F7`. Exit `0`, and the output is **byte for byte identical** to the shipped Python CLI run against the same daemon, with the corrected platform word in both. Two defects were fixed to reach that, `F1` and `F3`. |
| D2 | as D1, no provider connected | `vadgr providers` | each provider named with `not connected`; the list matches `GET /api/providers` | CLI output, `curl` body | none | **pass**: three providers, each `not connected`, matching `GET /api/providers`. Identical to the Python CLI. |
| D3 | as D1 | `vadgr computer-use status` | prints the enabled state, and the daemon line when the daemon sends one; equals `GET /api/settings/computer-use` | CLI output, `curl` body | none | **pass**: `Computer use: enabled`, matching `GET /api/settings/computer-use`. Identical to the Python CLI. |
| D4 | as D1, no runs | `vadgr runs list` | "No runs found." and exit `0`, not an empty table | CLI output | none | **pass**: `No runs found.` and exit `0`, not an empty table. |
| D5 | one run in the database | `vadgr runs list` | a table with `Run ID`, `Task`, `Status` and `Duration`; the id column is the first 8 characters | CLI output, `curl /api/runs` | none | **pass** after F1 and F2: seven runs, one row each, every line 91 columns wide, ids at eight characters, and the `Duration` column carrying real durations. |
| D6 | as D5 | `vadgr runs get <first 8 chars>` | resolves the prefix to the full id and prints the detail block; the fields equal `GET /api/runs/<id>` | CLI output, `curl` body | none | **pass**: `run-10e5` resolved to the full id, every field equals `GET /api/runs/<id>`, and the failed run printed `Error: NO_ACTION_TAKEN` and its resume hint. |

## Part E: provider onboarding through the new CLI

Against the **Rust** daemon, with one real credential read from `../.env` and
never printed.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| E1 | fresh database; `GEMINI_API_KEY` exported into the command's environment only | `vadgr provider login gemini` | says it is using the environment variable by **name**, connects, and reports either `Ready:` or `Connected:`; `GET /api/providers` shows Gemini connected | CLI output with no secret in it, `curl` body, `grep` of the database for the secret returning zero | E6 | **pass**: `Using GEMINI_API_KEY.` names the variable and never the value, the connection reported `Ready: Google Gemini, Gemini 3.7 Flash`, and the daemon shows Gemini connected and default with a live 28 model catalog. The key appears **zero** times in the database, the WAL, the SHM and this evidence file. |
| E2 | E1 connected | `vadgr provider status` | Gemini listed connected, with its catalog; equals `GET /api/providers` | CLI output, `curl` body | E6 | **pass**: Gemini connected and default with its catalog; OpenAI and Anthropic not connected. |
| E3 | as E2 | `vadgr provider status --refresh` | exit `0`; the catalog is re-read live and still lists models | CLI output, daemon log line for the refresh | E6 | **pass**: exit `0`, 28 models still listed, and the daemon logged `POST /api/providers/gemini/catalog-refresh` at `200` in 176 ms. |
| E4 | as E2 | `vadgr model list` | only connected providers, with their model ids and names | CLI output | E6 | **pass**: only Gemini is listed, and the model chosen for this pass, `gemini-3.5-flash-lite`, is in it. |
| E5 | as E2 | `vadgr model default gemini/<a model from E4>` | exit `0`, prints `Default: gemini / <model>`; `GET /api/providers` shows `is_default` on Gemini with that `default_model` | CLI output, `curl` body | E6 | **pass**: `Default: gemini / gemini-3.5-flash-lite`, and `GET /api/providers` agrees on both the provider and the model. |
| E6 | as E5 | `vadgr provider logout gemini` | exit `0`, prints `Disconnected: Google Gemini`; the connection and its credential record are gone | CLI output, `curl` body, credential directory listing | none | **pass**: the daemon refused with `the default provider cannot be disconnected`, exit `1`, and Gemini stayed connected and default. **The cell as first written could not pass**, because it logged out the provider `E5` had just made default; it is split, and `E6b` carries the successful case. |
| E6b | `E6`'s state, Gemini still default | connect Anthropic from `ANTHROPIC_API_KEY`, then `vadgr provider logout anthropic` | the second provider connects without moving the default, and logging it out removes its connection and its credential record | CLI output, `curl` body, credential directory listing | none | **pass**: Anthropic connected from `ANTHROPIC_API_KEY` with `Default remains: Google Gemini / gemini-3.5-flash-lite`, then `vadgr provider logout anthropic` exited `0`, printed `Disconnected: Anthropic`, and left exactly one credential record, Gemini's. |

## Part F: a run, watched

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| F1 | provider connected and default | `vadgr run "<task>" --background` | exit `0`, prints the run id and the watch hint, and returns immediately; the run exists in `GET /api/runs` | CLI output, `curl` body | the run finishes on its own | **pass**: exit `0` in 20 ms, printing the run id and the watch hint; the run reached `completed` in 2 iterations for 1,496 input and 86 output tokens. **The first attempt failed and it was the harness**: the task asked only for a reply, and this engine fails a turn that takes no action (`NO_ACTION_TAKEN`). |
| F2 | as F1 | `vadgr run "<task>"` watched to the end | the spinner reports progress, then `Run completed (<duration>)` and a `See results:` line; exit `0`; the journal shows the run reached `completed` | CLI output, run row, journal | none | **pass**: `Run completed (2s)` then the `See results:` line, exit `0`, and the run row reads `completed`. |
| F3 | a run started and cancelled from another terminal through `vadgr runs cancel` | `vadgr run "<task>"` watching when the cancellation lands | **the watcher says the run was cancelled** and exits `0`. Against the Python CLI this printed nothing at all | CLI output, the run row's `cancelled` status, the socket frames | none | **pass, and this is the improvement the release exists for**: the watcher printed `Run cancelled (4s)` and exited `0`, and the row read `cancelled`. **The shipped Python CLI was driven against the same daemon for the same cancellation and printed nothing at all, and was still hanging 16 seconds later** (`F/F3-python-comparison.txt`). |
| F4 | as F1 | `vadgr run "<task>" --background --json` | prints the run row as JSON, parseable, containing the same id the API reports | CLI output piped through `jq`, `curl` body | none | **pass on `d1b3f2f`**, re-run after `F11`. The whole stdout parses on its own with no slicing, and its `id` equals the one `GET /api/runs/<id>` serves; the hint is still printed when the caller did not ask for JSON. **The earlier WSL pass on this cell was wrong and is retracted**: the hint was on stdout, visible in that run's own captured output, and the oracle sliced from `{` to `}` instead of parsing the stream. `jq` is not installed on this host, so the strict parse is the whole stream through `json.load`, which fails on any trailing text. |
| F5 | any state | `vadgr run "<task>" --provider gemini` | exit `2`, usage error naming that `--provider` and `--model` go together | CLI output on stderr | none | **pass**: exit `2`, `--provider and --model must be given together.` |
| F6 | any state | `vadgr run "   "` | exit `2`, usage error: an empty task is not a run | CLI output on stderr | none | **pass**: exit `2`, `TASK must not be empty.` |

## Part G: pairing, and a QR that carries the right link

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| G1 | Rust daemon, no provider connected | `vadgr pair` with no terminal for the prompt | says a provider must be connected first and stops without minting a code; no pairing row is created | CLI output, `curl /api/devices` | none | **pass**: with no provider connected the command said `Before this machine can pair, connect a model provider.`, offered the provider choice, and stopped without minting anything. `GET /api/devices` returned `[]`. |
| G2 | provider connected and default | `vadgr pair` | prints a QR, then `Machine`, `Address` and `Pairing code`, then the one-time validity line; exit `0` | CLI output including the rendered symbol | the code expires | **pass**: a 41 by 21 symbol, then `Machine`, `Address` and `Pairing code`, then the one-time line; exit `0`. The address is the tailnet name the transport advertises. |
| G3 | G2's output | rebuild the deep link from the printed `Machine`, `Address` and `Pairing code`, encode it at the shipped settings, and compare with the rendered symbol | the two renders are identical, so what is on the screen encodes exactly the link the phone needs | the two renders and their comparison | none | **pass**: `rqrr`, a decoder independent of the encoder under test, read the symbol **as printed** and recovered `vadgr://pair?host=santiago-casa-1.tail323b9e.ts.net&port=8811&token=N36R-GRHC&name=Santiago-Casa`, which is exactly the link rebuilt from the fields printed beside it. Version 5 at error correction level `Low`, as the probe chose. |
| G4 | G2's QR on screen, handset in the owner's hand | the owner scans it with the Vadgr app | the app reads the machine name and address and pairs | the owner's confirmation and the device row the daemon records | the device is removed | **pass**: the owner scanned the symbol the installed `vadgr pair` printed, with the Vadgr app on a handset over the tailnet. **The verdict is the daemon's, not the owner's report**: `POST /api/auth/claim` answered `200` at `22:07:24` where every earlier probe with an unminted code answered `401`, and `GET /api/devices` then carried one row, `Xiaomi 2406APNFAG`, `paired_at 22:07:24`. Its `last_seen` is later than its `paired_at`, so the phone came back and talked to the machine rather than only completing the claim. **The first attempt did not pair and that is recorded rather than retried away**: no claim reached the daemon at all, because the code had expired, and the cell was re-run inside the five minute window. |

## Part H: the failures a script branches on

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| H1 | nothing listening on the configured port | `vadgr health` | exit `3`, "API is not running at ... Start it with: vadgr start", and it answers in well under a second rather than after the request timeout | CLI output, wall-clock duration | none | **pass**: exit `3` with `API is not running at http://127.0.0.1:59997. Start it with: vadgr start`, answered in **1.509 s**, which is the shipped 1.5 s connect timeout rather than the 15 s an unprobed request takes on WSL2. |
| H2 | any state | `vadgr runs get` | exit `2` with usage on stderr | CLI output | none | **pass**: exit `2` with usage on stderr. |
| H3 | Rust daemon with runs, none matching | `vadgr runs get zzzzzzzz` | exit `1`, "No run matching 'zzzzzzzz' found." | CLI output | none | **pass**: exit `1`, `No run matching 'zzzzzzzz' found.` |
| H4 | Rust daemon | `POST /api/runs` through the CLI with a body the daemon rejects at validation | the message names the field that failed rather than printing a bare status | CLI output | none | **partial**: the daemon's `422` was captured live and its body is the list shape the parser reads, `{"detail":[{"msg":"...missing field `task`..."}]}`. **No public CLI invocation can produce it**, because the CLI never sends a malformed body, so the parsing itself is covered by its unit test rather than by this cell. The nearest CLI case, an unknown model, is served as a run failure and the watcher reported it correctly at exit `1`. |
| H5 | Rust daemon | `vadgr health > file` and `vadgr runs list > file` | the files contain no escape sequence; the same commands on a terminal are coloured | the two files, and a byte scan for `0x1b` | none | **pass**: `health`, `runs list` and `status` redirected to files contain zero escape bytes. |


## Per-OS results

Legend: `pass` and `fail` mean it ran. `blocked` means it could not run, and says
what stopped it. `not run` means nobody ran it, which is honest and visibly owed.
`Not-Needed` means there is genuinely no OS-specific surface in that part, and it
is only ever written with its reason. **A cell is marked from observation, never
expectation.**

**The automated gate is not an e2e pass.** CI builds an environment and runs the
unit suites. It drives no session and calls nothing over the wire, so a green CI
row says the suites pass on that OS and nothing about whether the product works
there. The `overall` row never inherits a gate result: it is the weakest of the
parts actually driven on that OS.

| part | WSL | Linux | Windows native | macOS | notes |
|---|---|---|---|---|---|
| automated gate: build, test, lint | **pass** | **pass** | **partial**, api only | **pass**, run locally: rust 272, api 445, cli 150, engine 122, fmt and clippy at 0 | run locally on each host. **The rust figure differs by platform and that is correct**: `tailscale.rs` carries three tests gated to macOS, so the same tree is 269 on Linux and WSL and 272 on macOS. Native Linux measured **rust 269** (267 before this pass, plus the two the port fix added), api 445, cli 150, engine 122, with `cargo fmt --check` and `cargo clippy --all-targets -- -D warnings` at exit `0`. **Windows**: the api suite runs 445 and 436 pass; the 8 failures are named in `F8` and every one of them predates this branch, proved by re-running them with the branch's changes stashed. The Rust suites were not re-run on Windows. **The green WSL figure above hides something this row must not**: `bash` on Windows resolves to `C:\WINDOWS\system32\bash.exe`, the WSL launcher, so the suite's subprocess tests that shell through `bash` leave Windows to pass |
| A: the binary is the built head | **pass**, 3 of 3 | **pass**, 3 of 3 | **pass**, 3 of 3 | **pass**, 3 of 3 | the installed command resolves inside the test root and its `sha256` is the release build of the head under test |
| B: address resolution and the rename | **pass**, 6 of 6 | **pass**, 6 of 6 | **pass**, 6 of 6 | **pass**, 6 of 6 | includes the two cells that matter most for the rename: a live port file beating the environment, and the old `FORGE_*` names reaching nothing |
| C: the service group, Python daemon | **pass**, 8 of 8 | **pass**, 8 of 8 | **pass**, 8 of 8 | **pass**, 8 of 8 | the Rust CLI starts, supervises, follows and stops the **Python** daemon, which is the strangler seam this release must not break |
| D: read-only commands, Rust daemon | **pass**, 6 of 6 | **pass**, 6 of 6 | **pass**, 6 of 6 | **pass**, 6 of 6 | `health`, `providers`, `computer-use status` and `status` are byte for byte identical to the shipped Python CLI on the same daemon. Two defects were fixed to get there, F1 and F3 |
| E: provider onboarding | **pass**, 7 of 7 | **pass**, 7 of 7 | **pass**, 7 of 7 | **pass**, 7 of 7 | two real credentials, a live 28 model catalog and a live 10 model catalog, one bounded readiness call each, and the secret absent from the database, WAL, SHM and evidence. **Windows**: re-driven from a fresh database against a daemon on `18816`, because an earlier drive on this OS left no re-readable captures and corroboration is not evidence. `E1` named `GEMINI_API_KEY` rather than its value and reported `Ready: Google Gemini, Gemini 3.7 Flash`; `E3` was proved live by the daemon's own `POST /api/providers/gemini/catalog-refresh status=200` in `153 ms`; `E6` refused with `the default provider cannot be disconnected` exactly as it does on WSL; `E6b` connected Anthropic's 10 model catalog, printed `Default remains: Google Gemini / gemini-2.5-flash-lite`, and its credential record went from two files to one on logout. **The secret-absence oracle was run with the daemon stopped**, because a first attempt could not read the database, WAL, SHM or daemon log while it held them open and would have reported a clean scan of the files that mattered least: 22 files, zero plaintext occurrences of either key, and the credential store's ACL is owner plus `OWNER RIGHTS` and `SYSTEM` only |
| F: runs and the watcher | **pass**, 6 of 6 | **pass**, 6 of 6 | **pass**, 6 of 6 | **pass**, 6 of 6 | `F3` is the release's own improvement, and it is proved by driving the shipped Python CLI against the same cancellation, where it printed nothing and hung |
| G: pair and the QR | **pass**, 4 of 4 | **pass**, 4 of 4 | **pass**, 4 of 4 | **pass**, 4 of 4 | `G3` decodes the printed symbol with an independent decoder; `G4` is a real handset, and the daemon recorded the claim at `200` and the device row |
| H: negatives and exit codes | **pass**, 4 of 5, 1 partial | **pass**, 4 of 5, 1 partial | **pass**, 4 of 5, 1 partial | **pass**, 4 of 5, `H4` partial | `H4` is partial: no public CLI invocation can send a malformed body, so the `422` parser is covered by its unit test and the wire shape by a live probe |
| **overall** | **pass**, 1 partial, re-run on `0a7fb17` | **pass**, 1 partial | **pass**, 1 partial | **pass**, 44 of 45, 1 partial | **Windows**: every part driven to its stated oracles, 44 of 45 pass. `G3` used this runbook's own `harness/qr-decode`, which builds and runs unchanged here: `rqrr` read the symbol **as printed** and recovered `vadgr://pair?host=santiago-casa.tail323b9e.ts.net&port=18811&token=6Z6E-6DQH&name=Santiago-Casa`, the link rebuilt from the fields beside it, at version 5 and ecc level Low. `H4` is partial and **earned rather than inherited**: the `422` was captured live on this OS, its body is the list shape the parser reads, and its message names the field, `missing field \`task\``. One product defect was found and fixed on this OS (`F7`), and one earlier finding was **retracted** (`F9`) | every part of this runbook has been driven on WSL and every cell has a verdict. The one row that is not a clean pass is named above and it is not a WSL defect: `H4` has no public path to it. Three defects were found and fixed during the WSL pass, each with a regression test seen red first. **Four cells were then re-run on `d1b3f2f`** after the native Windows pass fixed two more: `B1`, `C1` and `D1` for `F7`, which changed the platform field on every OS, and `F4` for `F11`, whose earlier WSL pass is retracted because a lenient oracle hid the defect. **`C8` was then re-run again on `0a7fb17`** after macOS found `F15` in the port search, and the flip that defect needs was reproduced on this host before the cell was re-driven |

**Native Linux, driven 2026-08-19 at `bc7921d`.** Ubuntu 26.04, GNOME on a
Wayland session, not WSL. The owner cell ran first in the sense the rules mean:
the tailnet this host lacked was installed and authenticated before any
unattended cell, and `G` was reached as early as its own dependencies allow,
since `G2` needs a connected default provider and so cannot precede `E`.

Every part passes. `G4` paired a real handset, `Xiaomi 2406APNFAG`, over the
tailnet at `ubuntu26-04.tail323b9e.ts.net:8811`, and the verdict is the
daemon's: `POST /api/auth/claim` answered `200` at `02:48:32` where an earlier
expired code answered `401` at `02:03:10`, and the device row's `last_seen` is
`02:48:37`, later than its `paired_at`, so the phone came back and talked to the
machine rather than only completing the claim. Two codes expired unscanned
before it and that is recorded rather than retried away. `F3` printed
`Run cancelled (10s)` and exited `0`, which is the release's own improvement.
`H1` answers in **13 ms** here rather than the 1.5 s connect timeout WSL and
Windows see, because a refused loopback connection on Linux returns at once.

Three findings came out of it. `F12` and `F13` are defects in this runbook's own
handoff, both found by being the first host to follow it literally, and both
fixed here. `F14` is a harness fault of this pass, recorded as one rather than
filed against the product.

Process supervision, path handling, terminal rendering and the loopback probe are
platform-shaped. **No supported operating system is `Not-Needed` for final
acceptance.**

## Findings

Every defect here was found by looking at what the CLI printed, next to what the
shipped CLI prints, against the same daemon. **None of them was visible to a unit
test**, because each test asserted what the port produced rather than what the
product produces. That is section 2.0a's warning arriving in practice: the sweep
asserts argv, exit code and whether output was produced, and reads none of it.

| # | what | where | disposition |
|---|---|---|---|
| F1 | **The table was the wrong shape and colour broke its layout.** The shipped CLI draws `rich.Table(box=None)`: padded columns, two spaces apart. The port drew a full UTF-8 box. Worse, a styled cell carries escape bytes that occupy no columns, so the layout counted them: `Status` was drawn eighteen columns wide for a seven character word and every row under it landed short | `C3`, `D5` | **fixed** in `3a804be`. Widths now come from `unicode-width` on the unstyled text. The regression test compares the styled and unstyled renders and was seen red against the raw measurement. `comfy-table` leaves with the box, and `unicode-width` came with it, so the change removes a dependency |
| F2 | **The `Duration` column never carried a duration.** No daemon sends a `duration` field, so the Python CLI printed a dash for every run and the port copied that faithfully. A column that never carries the thing it is named after is worse than no column | `D5`, `D6` | **fixed** in `1953ec7`. Computed from the `started_at` and `completed_at` the same row already carries. A daemon-supplied duration still wins; a running run stays a dash; a backwards clock is not a negative run |
| F3 | **The key-value block lost its indent and its colon, and five statuses lost their colour.** The shipped CLI prints `  Status:       healthy`; the port printed `Status       healthy`. And `error`, `available`, `not found`, `not running` and `stopped` were missing from the palette, so `health`'s module block and the `status` table printed plain where the product colours them | `D1`, `C3` | **fixed** in `e3799b1`. `vadgr health` is now byte for byte identical to the shipped CLI on the same daemon. The new test walks every status the CLI can print |
| F4 | `vadgr runs list` **truncates** a long task where the shipped CLI wraps it across three or four lines at a 120 column width | `D5` | **intended, not a defect.** The build spec asks for truncation measured by display width rather than bytes (section 8), so one run is one row. Recorded here because a reader comparing the two CLIs will see it |
| F5 | The `422` path cannot be reached through a public CLI invocation, because the CLI never sends a malformed body | `H4` | **partial, and recorded rather than worked around.** The daemon's `422` body was captured live and it is the list shape the parser reads. The parsing is covered by its unit test. Inventing a CLI call that sends a broken body would test the harness, not the product |
| F6 | The first `F1` attempt failed with `NO_ACTION_TAKEN` | `F1` | **the harness, not the product.** The task asked the model only to reply, and this engine fails a turn that takes no action. The task was corrected and the cell re-run. Recorded because the same mistake will be made again by whoever writes the next runbook |

| F7 | **The daemon told every owner their machine was WSL.** `/api/health` and `/api/computer-use/status` returned a hard-coded `"wsl2"`, and the phone prints that string verbatim in its machine row, so a native Windows box reported itself as WSL. The word was wrong on WSL too: the Rust daemon answers the same route with `"wsl"`, so the published vocabulary depended on which of the two daemons replied | `B4`, seen on the wire driving `vadgr health` against the Python daemon on Windows | **fixed** in `37a9b0b`. `api/utils/platform.py` now mirrors `rust/src/platform.rs`, container carve-out included, and computer-use keeps its own `wsl2`/`native` vocabulary because it answers a different question. Thirteen tests added, the route test seen red first as `assert 'wsl2' == 'windows'`. **This fix changes `/api/health` output on every operating system, so by rule 4 it invalidates the WSL cells that read the platform field: `B1`, `C1` and `D1` are owed a re-run there** |
| F8 | **The api suite does not pass on native Windows, and its green WSL figure is partly an illusion.** Eight tests fail here: seven in `TestCLIAgentProvider` because they invoke `echo` and `sleep`, which are not executables on Windows, and one in `test_transport` because it builds an `AF_UNIX` socket. Worse than the failures: `bash` resolves to `C:\WINDOWS\system32\bash.exe`, the **WSL launcher**, so every subprocess test that shells through `bash` is green because it left Windows, not because Windows works | the automated gate row | **recorded, not fixed, and deliberately so.** All eight predate this branch, proved by re-running them with the branch's changes stashed and getting the identical eight. Porting the suite's POSIX assumptions is test-only work, unrelated to this minor's subject, and folding it into this PR would hide a real body of work inside a CLI change. **It is owed, and naming it here is the point** |
| F9 | `vadgr start` **never returns on Windows** | `C1`, reported twice and acted on once | **retracted: the harness, not the product.** PowerShell's `Start-Process -Wait` and `2>&1 \|` pipelines block on the handle the detached daemon inherits, so the CLI had exited and the terminal had not noticed. Measured directly, `start` exits in `3.5s` and `restart` in `6.2s`. A `DETACHED_PROCESS` change was written for this and **reverted** once the original code was shown to behave identically, rather than shipped as a fix for nothing. Nine cells were reported blocked by it and none of them were |
| F16 | **The `F15` regression test did not build on Linux or WSL.** Its helper names `sin_len` on `libc::sockaddr_in`, a field the BSDs and macOS carry and Linux does not have at all, so `cargo test` failed to compile rather than failing a test. Its precondition then asserted that the connect probe flips on the **second** call, which is macOS behaviour: Linux's effective accept queue is larger than the backlog asked for, so it answers `in use` again first | the whole Rust suite, on WSL | **fixed here**: the helper zeroes the struct and sets `sin_len` only on Apple targets, and the flip is now a bounded observation rather than a fixed-position assertion. The test still fails for the real reason, and it still asserts the invariant the fix promises. **A regression test that only builds on the operating system that wrote it protects one platform and blocks the others** |
| F11 | **`--background --json` printed a hint on stdout, so the output the flag calls machine readable was not valid JSON.** The run row was followed by `Watch it with: vadgr runs get <id>` on the same stream | `F4`, found by driving the CLI on native Windows | **fixed** in `ae16ff1`: the hint is printed only when the caller did not ask for JSON, because it is what a person needs after starting a background run and it simply cannot share stdout with the object. A new integration test stands up a daemon stub and asserts stdout parses on its own; it was seen red against the reverted line. **The WSL pass had marked `F4` a pass, and that was wrong**: the hint is in that run's own captured output, and the oracle sliced from `{` to `}` rather than parsing the stream, so a lenient parse hid the defect it was there to catch. Re-run on WSL against `d1b3f2f` |
| F10 | `vadgr health` against a dead port answers in `1512 ms` on Windows, where the cell expects "well under a second" | `H1` | **the platform, not a defect, and no fix attempted.** A closed IPv4 loopback port on this host takes `2000 ms` to refuse, on `127.0.0.1` and on `localhost` alike, while `::1` refuses the same port in under `5 ms`. That is the Windows and WSL loopback forwarding layer swallowing the reset, the same behaviour `client.rs` already documents for WSL2. The CLI's own `1500 ms` `CONNECT_TIMEOUT` is what bounds the wait, so the cell's real contrast holds: `1.5s`, not the `15s` request timeout. **No faster probe is sound**, because a daemon bound only to `127.0.0.1` cannot be ruled out by `::1` refusing |
| F12 | **The handoff's own build step names a binary that has never existed.** Step 2 says `cp target/release/vadgr`, and the crate declares `vadgr-daemon` and `vadgr-cli`; nothing has ever built a `target/release/vadgr`. The first host to follow the handoff literally stopped four lines in with `cannot stat 'target/release/vadgr'`. | the remote-host handoff, step 2 | **fixed on the native Linux pass.** The line now reads `cp target/release/vadgr-cli "$E2E_HOME/bin/vadgr"`, which is the rename that puts the product's own name on the installed command. WSL and Windows passed because both had already built and copied by hand before the step was written down, which is exactly the gap a handoff exists to close. |
| F13 | **The credential availability check assumes one host's variable names.** The owner table said `grep -c '^GEMINI_API_KEY=' ../.env` must return `1`. On this host the file carries `GEMINI`, `OPEN_AI` and `ANTROPHIC`, so the stated check returns `0` and a host following it literally would mark the whole `E` group blocked with a live key sitting in the file. | the owner and environment requirements table | **fixed on the native Linux pass.** The row now accepts a machine-local alias and says the driver maps it to the portable name in that command's environment only, which is the form `0.4.7`'s handoff already used. The `E` group ran unchanged: `vadgr provider login gemini` printed `Using GEMINI_API_KEY.` because the portable name is what the command's environment carried. |
| F14 | The first `B5` attempt left both files in place | `B5` | **the harness, not the product.** The fixture was written to `$VADGR_HOME` because the prerequisites gloss that path as "pid files, port files, api.log", and the CLI keeps them in `$VADGR_HOME/pids/`. The CLI never saw the fixture, so it correctly fell to the default port and the files it had not read survived. Re-staged under `pids/` the cell passes as written: both files removed, default port, exit `3`. |
| F15 | **`vadgr start` could not survive a busy port.** `C8` put a listener on the configured port and started the daemon. It printed `Port 8815 busy, using 8815`, naming the same port twice in one sentence, and the daemon then died on bind. | `find_free_port` starts at offset zero, so the first candidate it tests is the port the caller has just been told is busy, and it re-tests with `port_in_use`, which answers by **connecting**. A listener that is not accepting fills its backlog on the first probe and refuses every later one, so two probes in a row disagree: busy, then free. Reproduced directly outside the product: probe 1 `busy`, probes 2 to 4 `free`. Connecting answers "is a daemon alive"; binding answers "can I take this port". The search was asking the wrong one. | The search decides by binding, which is the question it is actually asking and does not depend on what the holder does with its accept queue. `port_in_use` is untouched and still answers liveness. Two tests: the search test holds a port with a backlog of one and asserts the probe flips **before** asserting the search skips it, so it fails for the real reason rather than by luck. `libc` is a dev dependency because std cannot express a socket that is bound and not accepting. | **fixed** in `00055b3`. `C8` re-run against the rebuilt binary prints `Port 8815 busy, using 8816`, the port file names 8816 and health answers there. Without the fix the test reports `the search returned the held port`. rust 272, fmt and clippy clean. **Rule 4**: `C8` is owed again on WSL, native Linux and native Windows, because the port search is shared code and their passes observed the old behaviour. **Native Windows has re-run it on `d80c692`**, and `B4` with it, because that cell's precondition is the walk-up itself and so observed the old search too: `Port 18812 busy, using 18813`, the port file names `18813`, health answers there, and `vadgr health` reaches `18813` while `VADGR_PORT` still says `18812`. **This defect was on Windows first and was written off there as a harness fault.** The same probe disagreement reproduces on this host, `busy` then `free` three times over, and the Windows pass saw `Port 18812 busy, using 18812` during `B4` setup, blamed its own squatter's backlog, fixed the squatter and moved on. Suspecting the harness is the right instinct and it stopped one question early: the harness had produced the condition, and the product's response to that condition was still wrong. |
| F16 | **On Apple Terminal the QR is sliced by the line gap.** The owner photographed it: every printed row of the symbol carries a horizontal band through it, where the same command on Linux and Windows terminals renders solid. | `render_qr` packs two module rows into one printed line using the half block glyphs, so the symbol is only continuous if the terminal draws consecutive lines with no vertical gap. Apple Terminal leaves one. The code already handles the neighbouring problem, inverting for a dark background with a comment that a QR drawn the wrong way round does not scan, so the class of issue was known and this member of it was not. | Not fixed, and not a failure. **The owner scanned it from the screen and the handset paired**, so the symbol is readable at the default font size on this host, and `G4` is a real pass rather than a workaround. | **observation**. Worth recording for two reasons. A smaller font or a fussier camera has less margin than this pass happened to have. And `G3` cannot detect this class of defect at all: it rebuilds the module matrix from the **characters** the CLI emitted, so it proves the encoder while saying nothing about what the screen shows. The gap between "the characters are right" and "the picture scans" is exactly where this lives, and only `G4` covers it. |
| F15 | **The handoff assumed the tooling of the hosts that had already run it.** The environment table required a "WSL2 host" for every cell and checked the ports with `ss -ltn`; the prerequisites hashed the installed binary with `sha256sum`; and `B4`, `C6` and `C8` named `ss -ltn` as their oracle. macOS has neither command, so a macOS session reading this runbook would have stopped at the prerequisites, and the host requirement named the wrong operating system for two of the four targets. | the owner table, the prerequisites, and the `B4`, `C6` and `C8` evidence columns | **fixed on the native Linux pass, before macOS was asked for anything.** The host row now says "the host under test" and names the listener check for each of the three families; the hash line names `shasum -a 256` for macOS; and the three cells name "the listener list" rather than one platform's command. Found by reading the runbook as the next host rather than by running it, which is what `F12` and `F13` cost this pass by not doing. |

## Surface coverage - **every published endpoint, with what it returned**

Generated from the recorded sweep, never typed. The recorder invokes the
installed `vadgr` binary and calls the daemon's routes directly, writing request,
status, error code and body to `sweep/record.json`; these tables are emitted from
that record by `sweep/tables.md`'s generator.

### Shipped

| endpoint | what was asked | status | code | response, as returned |
|---|---|---|---|---|
| `GET /api/health` | the daemon is up | `200` | - | `{"modules":{"computer_use":false},"platform":"wsl","status":"healthy","transport":{"advertise_host":"santiago-casa-1.tail323b9e.ts.net","available":true,"bind_host":"100.67.110.10","name":"tailscale"}` |
| `GET /api/providers` | the provider list | `200` | - | `[{"auth_method":null,"auth_methods":["oauth","api_key"],"available":false,"catalog_stale":false,"catalog_verified_at":null,"connected":false,"default_model":null,"id":"openai","is_default":false,"kind` |
| `GET /api/settings/computer-use` | the computer-use setting | `200` | - | `{"daemon":null,"enabled":true,"platform":"wsl2","venv_ready":false}` |
| `GET /api/computer-use/status` | the runtime's own status | `200` | - | `{"available":false,"platform":"wsl2"}` |
| `GET /api/devices` | paired devices | `200` | - | `[]` |
| `GET /api/runs` | the run list | `200` | - | `[{"agent_name":"Use your todo tool to note one step and mark it completed, then finish.","completed_at":"2026-08-18T18:29:16.718888+00:00","id":"run-5fddb1d2525a40f1b1838eef43949830","inputs":{"task":` |
| `GET /api/runs/run-5fddb1d2525a40f1b1838eef43949830` | one run | `200` | - | `{"agent_name":"Use your todo tool to note one step and mark it completed, then finish.","completed_at":"2026-08-18T18:29:16.718888+00:00","id":"run-5fddb1d2525a40f1b1838eef43949830","inputs":{"task":"` |
| `POST /api/runs/run-5fddb1d2525a40f1b1838eef43949830/cancel` | negative: cancelling a finished run | `409` | `RUN_NOT_ACTIVE` | `{"error":{"code":"RUN_NOT_ACTIVE","details":{},"message":"Run is already finished"}}` |
| `POST /api/runs/run-5fddb1d2525a40f1b1838eef43949830/resume` | resume | `409` | `RUN_NOT_RESUMABLE` | `{"error":{"code":"RUN_NOT_RESUMABLE","details":{},"message":"Only failed runs can be resumed (current status: completed)"}}` |
| `GET /api/runs/run-does-not-exist` | negative: no such run | `404` | `RUN_NOT_FOUND` | `{"error":{"code":"RUN_NOT_FOUND","details":{},"message":"Run with id 'run-does-not-exist' not found"}}` |
| `POST /api/runs` | negative: no task | `422` | - | `{"detail":[{"msg":"Failed to deserialize the JSON body into the target type: missing field `task` at line 1 column 2","type":"value_error"}]}` |
| `POST /api/auth/pair` | mint a pairing code | `200` | - | `{"host":"santiago-casa-1.tail323b9e.ts.net","machine_name":"Santiago-Casa","pairing_token":"3PEF-0SW7","port":8811}` |
| `POST /api/auth/claim` | negative: a code that was never minted | `401` | `PAIRING_CODE_INVALID` | `{"error":{"code":"PAIRING_CODE_INVALID","details":{},"message":"That pairing code is wrong or has already been used."}}` |
| `POST /api/providers/gemini/catalog-refresh` | refresh a connected catalog | `200` | - | `{"auth_method":"api_key","auth_methods":["api_key"],"available":true,"catalog_stale":false,"catalog_verified_at":"2026-08-18T18:37:10.260072+00:00","connected":true,"default_model":"gemini-3.5-flash-l` |
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
| `vadgr --version` | `0` | stdout | `vadgr 0.4.8` |
| `vadgr health` | `0` | stdout | `Status:       healthy` |
| `vadgr providers` | `0` | stdout | `OpenAI (openai) -- not connected` |
| `vadgr computer-use status` | `0` | stdout | `Computer use: enabled` |
| `vadgr runs list` | `0` | stdout | `Run ID    Task                                                          Status     Duration` |
| `vadgr runs` | `0` | stdout | `Run ID    Task                                                          Status     Duration` |
| `vadgr runs get run-5fdd` | `0` | stdout | `Run ID:       run-5fddb1d2525a40f1b1838eef43949830` |
| `vadgr runs cancel run-5fdd` | `1` | stderr | `Error: Run is already finished` |
| `vadgr runs resume run-5fdd` | `1` | stderr | `Error: Only failed runs can be resumed (current status: completed)` |
| `vadgr runs get zzzzzzzz` | `1` | stderr | `Error: No run matching 'zzzzzzzz' found.` |
| `vadgr provider status` | `0` | stdout | `OpenAI: not connected` |
| `vadgr model list` | `0` | stdout | `Google Gemini: connected (default)` |
| `vadgr status` | `0` | stdout | `Service  PID  Status ` |
| `vadgr logs --no-follow -n 2` | `0` | stdout | `INFO:     Application shutdown complete.` |
| `vadgr update --check` | `0` | stdout | `[vadgr] vadgr is up to date.` |
| `vadgr run    ` | `2` | stderr | `Error: TASK must not be empty.` |
| `vadgr run x --provider gemini` | `2` | stderr | `Error: --provider and --model must be given together.` |
| `vadgr runs get` | `2` | stderr | `error: the following required arguments were not provided:` |
| `vadgr not-a-command` | `2` | stderr | `error: unrecognized subcommand 'not-a-command'` |

18 shipped endpoint calls, 18 answered; 7 absence probes; 19 CLI invocations.


## Repeatability - **three independent passes**

Three passes ran **concurrently**, each with its own port, database, state root
and daemon, so they are three observations rather than one run watched three
times. Each connected a provider, ran a task and then recorded the whole surface.

| axis | 8821 | 8822 | 8823 |
|---|---|---|---|
| HTTP entries | 18 | 18 | 18 |
| absence probes | 7 | 7 | 7 |
| CLI entries | 19 | 19 | 19 |
| method, path, status and error code | same | same | same |
| argv, exit code and output produced | same | same | same |
| whole record, ids normalised | differs | differs | differs |

The whole-record row **differs on one thing only**, and it is not the product:
the model's own wording of its answer, `I have noted the step in the todo list`
against `I have noted the step using the todo tool`. Everything structural is the
same.

| pass | run status | input tokens | output tokens | iterations |
|---|---|---|---|---|
| 8821 | completed | 2698 | 80 | 3 |
| 8822 | completed | 2719 | 81 | 3 |
| 8823 | completed | 2587 | 76 | 3 |

**Read structurally, then by token count.** Every HTTP entry agrees on method,
path, status and **error code**; every CLI entry agrees on argv, exit code and
whether output was produced. With the run ids normalised, the only remaining
difference in the whole record is the model's own wording of its answer, which is
the model rather than the product.

The token counts are three different live calls rather than one result reused:
2,698 / 2,719 / 2,587 input and 80 / 81 / 76 output, at 3 iterations each. Three
identical counts would have been the thing to worry about.

**One part of the closing rule is owed.** The standard closes a runbook with
three separate *agents*. These three passes were driven concurrently by one
operator, so they rule out ordering effects and cross-run interference but not
operator bias. The three-agent close is owed before the runbook is final.

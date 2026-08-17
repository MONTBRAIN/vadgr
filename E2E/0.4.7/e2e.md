# 0.4.7 - provider onboarding precedes pairing: e2e runbook

A clean Vadgr installation can connect supported model credentials directly,
keep multiple providers, select one machine default, and complete real work
without an external model CLI in the request path.

> **Status: E2E run on WSL and native Windows, and now partially run on native
> Linux, 2026-08-17.** Native Linux drove every part of this runbook: the
> automated gate locally, the surface sweep, all 29 `A` cells including a live
> ChatGPT OAuth approval, all 8 `BL` credential cells, 21 of 25 `C` cells, the
> whole `D` hard-kill sequence, all 5 `E` dogfood cells and `OS-L` against
> GNOME Text Editor on Wayland. It is not a clean `pass`: six rows are blocked
> on Tailscale and four `C` cells are partial. **It found and fixed two real
> defects.** `F31`: the installed cua `shell` tool rejected every ordinary
> string command. `F34`: a cancelled run broadcast no terminal frame at all, so
> a client watching the socket hung while the row read `cancelled`. macOS
> remains `not run`.
>
> **Status of the earlier passes: E2E partially run on WSL, 2026-08-17.** The automated gates and the
> static Linux clean-install gate pass. The corrected WSL pass uses the installed
> terminal `vadgr` command, direct HTTP, both run WebSockets, the release Rust
> daemon, installed cua and the real agent loop. OpenAI Platform API key, Gemini
> API key and Anthropic API key onboarding and work pass. ChatGPT OAuth login,
> catalog, readiness, restart, work and query-free browser-page observation
> pass. Fresh pairing, stale catalog, reauthentication and multi-provider
> deletion checks also pass. The expired OAuth callback did not reach Vadgr
> because OpenAI rejected the aged authorization response. Native Linux, macOS
> and Windows remain `not run`.
> **20 findings, and the WSL surface is now closed. F20 is the release's
> largest: the OpenAI adapter sent a screen capture to the model as base64
> text, which put roughly 185,000 tokens into one request against a 200,000 per
> minute ceiling and reported the refusal as exhausted quota. The account was
> healthy throughout. Repairing it unblocked the whole dogfood group, and E01,
> E02, E03, E05 and F17 now pass with the owner's own desktop as the oracle.
> F19 passes against a wheel built from the `0.7.1` tag and installed without
> editable mode. S06, S07, C14, C15 and C17 now run through the product against
> an unreachable and a deterministic provider, which provider endpoint
> configuration made possible. Every remaining cell is `partial` for a stated
> structural reason rather than for want of running: S01 on an upstream
> rejection, C07 to C09 on a reply surface that belongs to `0.6.0`, E04 on a
> monetary disposition the owner owns, and F15 on the boundary correction
> itself. Native Linux, macOS and Windows remain out of scope for a WSL pass.**

## How a pass is run, before anything else in this file

**These four rules come first because every one of them was learned by breaking
it. They hold on every supported operating system, for every agent that drives
this runbook, and they are not negotiable against a deadline or a token budget.**

**1. Whatever needs the owner runs first.** Before a single automated cell,
read the whole matrix, list every cell that cannot proceed without a human, and
run those cells at the start of the pass. In this runbook that is `A01` to
`A06`, `A25` to `A29` and `S01`, which need one ChatGPT OAuth approval in a
browser, plus any control that needs elevation. The owner is not a resource you
discover you needed after four hours of work. A pass that reaches its end and
then asks for a browser click has wasted the owner's day and produced a runbook
that is still `not run` where it matters most.

**2. Do not stop the pass to report.** The pass runs to completion for the
operating system it is on. Findings, blocked cells, corrections and questions
are written into this runbook and the evidence as they happen, and they are
reported when the pass ends. The only thing that stops a pass is a cell that
physically cannot proceed without the owner, and rule 1 exists so that never
happens after the start. Reporting a blocker mid-pass, and waiting, converts one
run into many and leaves every later cell unexecuted.

**3. A bug you find is a bug you fix, here, now.** The purpose of this e2e is
not to catalogue defects. It is to establish that the product works on the
target operating system. So when a cell fails, you fix the code, you add a test
that fails without the fix and passes with it, you re-run the failing cell until
it passes, you commit and push to the PR branch, and only then do you carry on
with the rest of the matrix. **A finding recorded without a fix is a moved
problem, not a found one.** The fix ships on the PR branch as it is made; the
branch is the working surface, and holding a fix back to ask permission is the
mistake.

**4. A fix invalidates the cells it touched, on every operating system that
already passed them.** A shared-behaviour fix means the earlier passes were
observing different code. Name the affected cells in the finding, mark them
`not run` again on the operating systems that had passed them, and say in the
per-OS matrix which fix invalidated them. The host that made the fix re-runs
them itself. The other hosts re-run them from the PR branch before merge. **No
operating system inherits a result from a build that no longer exists.**

## The approach

The closing runs use the installed product and a real agent given a goal-level
task, per [`../README.md`](../README.md). The verdict comes from provider rows,
SQLite metadata, credential-file controls, HTTP and CLI records, both run
WebSockets, and `trajectory.jsonl`. The agent's prose is not evidence.

Both product surfaces are required:

- the API plus both run WebSockets, which is the phone path;
- the shipped `vadgr` CLI pointed at the Rust daemon, which is the on-box path.

The agent driver, version, prompt, and complete output must be captured in the
private evidence bundle. The prompt names an owner goal, not a tool call.

For this transitional minor, the installed terminal entry point can dispatch
to Python internally. The operator first puts the exact PR-head installation on
`PATH`, records `command -v vadgr` and its install target, then invokes only
`vadgr ...`. Direct `python -m cli`, product imports and Python drivers do not
close CLI or owner-flow cells. Public API and WebSocket cells use their real
wire and are required separately from the CLI cells. Scripts may prepare
isolated state, capture output and parse evidence after the commands run. They
cannot replace either product surface or choose the agent's actions.

## One command at a time, and read its output before the next

**Every product command is invoked on its own, and its output is read before the
next command is chosen.** This holds on every supported operating system and for
every agent that drives this runbook. A wrapper script that runs a whole group
in one shot is not an execution of that group, even when every command inside it
is the real public surface.

The failure it stops is specific. A batch prints one wall of output, so no line
can be attributed to the command that produced it. It reports one exit code, so
the exit codes of the commands inside it are never read, and **a result from a
command whose exit code you did not read is not a result**. A failure in the
middle is carried past by the lines printed after it, and the author writes down
the batch's outcome instead of each cell's. The batch also decides the order in
advance, which is exactly what an e2e must not do: what the previous command
returned is what tells you whether the next one is still the right one, and a
cell whose precondition was never observed is not a cell that ran.

So:

- Run one command. Read its output and its exit code. Record the cell. Then
  choose the next command.
- Never chain product commands with `&&`, `;` or a loop so that one invocation
  covers several cells.
- Never wrap a group in a driver script that logs in, runs, restarts and reads
  back without stopping.

A helper is still allowed exactly where it always was: it may build isolated
state **before** the group starts, and it may capture, sanitize or parse
evidence **after** a command has already run. It may not sequence the product
commands, and a file that does is a harness pretending to be an operator.

The exception is a single cell whose own definition is a loop or a matrix, such
as `BL05` and `BL06` staging one weakened control per isolated copy. There the
repetition is the cell, it is written that way in the table, and each iteration
still prints its own labelled result. If a reader cannot tell from the evidence
which command produced which line, the rule was broken whatever the file was
called.

## Superseded acceptance diagnostics

Evidence recorded before the F15 correction is retained because it found real
product defects and exercised the release daemon. Its live `pass`, `partial` or
`blocked` labels describe acceptance diagnostics only. They are not current E2E
verdicts. The current result for every live WSL cell below is `not run` until a
new row or replacement table names a terminal `vadgr` invocation and direct
public-wire evidence. Automated gate rows keep their stated results.

## Corrected WSL public-boundary execution

The replacement boundary is
`e2e_evidence/vadgr-0.4.7/20260816-235029-wsl-public-entrypoint/` at Vadgr
`9761f6a41a9265e3f93f2484ec4cd6eb0363fd55`. A fresh installer-shaped home put
its `vadgr` entry point first on `PATH`. The release daemon SHA-256 is
`5f3a59b79860c12eaf22732cb632d9554689652186530f720c1109ec7e80c276`.
Installed cua came from a noneditable `0.7.0` wheel and `vadgr-cua doctor`
reported all 33 tools. Direct `curl` and `wscat` calls exercised HTTP plus both
run sockets separately from the terminal CLI.

| provider path | terminal onboarding | explicit model run | exact usage and cost | public-wire and independent oracle | result |
|---|---|---|---|---|---|
| OpenAI Platform API key | `vadgr provider login openai --auth api-key`; 51 live catalog models; default committed | `run-113d330660434b1695a35cbb793272c0`, `gpt-5.6-luna`, 4 turns | 23,644 input, 547 output, USD 0.0053852 | HTTP, raw WS, mobile WS, CLI and journal completed; exact platform/session/cwd marker matched | pass |
| ChatGPT OAuth | `vadgr provider login openai --auth chatgpt`; 7 live catalog models; default committed | `run-00b9eb0f4655445391f5212c74b2a16b`, `gpt-5.6-luna`, 3 turns | 16,855 input, 181 output; subscription OAuth has no attributable API charge | HTTP, raw WS, mobile WS, CLI, journal and exact marker agree; later browser observation found `/auth/complete` with an empty query | pass |
| Gemini API key | `vadgr provider login gemini`; 28 live catalog models; OpenAI default unchanged | bounded rerun `run-19fa499edbf94542b5d7b4321447d597`, `gemini-3.5-flash-lite`, 2 turns | 15,499 input, 106 output, USD 0.0049147 | HTTP, raw WS, mobile WS, CLI and journal completed; one installed-cua call and exact marker matched | pass |
| Anthropic API key | `vadgr provider login anthropic`; 10 live catalog models; OpenAI default unchanged | `run-fd1af6af9bc6441393b3c0ff6c969655`, `claude-haiku-4-5-20251001`, 2 turns | 18,573 input, 160 output, USD 0.019373 | HTTP, raw WS, mobile WS, CLI and journal completed; one installed-cua call and exact marker matched | pass |

Each onboarding command returned success only after its live readiness adapter
observed nonzero input and output usage. The current public response intentionally
does not expose the exact readiness counts. Exact usage above is therefore the
separately bounded full agent run, not an invented readiness number. All three
connections and catalogs survived a release-daemon restart. Raw SQLite, WAL and
SHM scans did not contain any of the three credential values.

## Native Linux execution

Run on 2026-08-17 on a native Linux desktop: Ubuntu 26.04 LTS, GNOME on a
Wayland session, not WSL. The host had no build toolchain, no `pip`, no
`python3-venv` and no Rust, and its clock was two days behind, which would have
stamped every artifact wrongly; both were corrected before the first cell.

| artifact | identity |
|---|---|
| tested head | `14b995b6a7cc900e913f537380c100aa0f1fe8df` |
| release daemon | built from that head, SHA-256 `daebef3143449ba73f4ca696b7c77a16201f977c7aa783f8c5933a1cc8bb0e14` |
| installed cua | wheel built from the repaired tree, installed non-editable outside the checkout, `vadgr-cua doctor` reports all 33 tools |
| `vadgr` entry point | an installer-shaped home first on `PATH`, resolving to `/home/<owner>/.forge-e2e/bin/vadgr` |
| capture and input backends | portal screenshot, Mutter RemoteDesktop input, AT-SPI structured reads with `coordinate_trust: per_window` |

The automated gate ran locally on this host rather than in CI: engine 122, api
432, cli 152 and rust 199 passed with one Docker-only test ignored, and
`cargo fmt --check`, `cargo check --all-targets` and
`cargo clippy --all-targets -- -D warnings` each exited `0`. The api count is
432 rather than the 429 recorded for the WSL pass because `d5e66a3` added three
api tests after that sweep; it is not a divergence between platforms.

Every product command in this pass was invoked on its own and its output read
before the next was chosen, per the rule at the top of this file. Two groups
were first driven by a wrapper script that sequenced several commands, and both
were discarded and re-run one command at a time rather than kept.

| group | native Linux result |
|---|---|
| `A01`-`A06` ChatGPT OAuth | pass. One owner browser approval completed the flow; the account-scoped catalog returned exactly seven models, the committed record is an opaque `cred_v1_` `0600` file whose access and refresh tokens are absent from the database, WAL and SHM, the connection survived a restart byte-identically, and `run-24cc7d18cb0d4a19a9e77a840b6b3858` completed on `gpt-5.6-luna` in 5 iterations for 28,220 input and 184 output tokens with an exact read-back |
| `A07`-`A12` OpenAI Platform key | pass. 51 live models; `run-6f9db82c6d3941dcb13c89379cd1dbd1`, 4 iterations, 22,710 input and 204 output tokens, USD 0.0048 |
| `A13`-`A18` Gemini key | pass. 28 live models; `run-42b7d9e2bb7e41bc84a82579f1d60663`, 5 iterations, 39,496 input and 261 output tokens, USD 0.0125 |
| `A19`-`A24` Anthropic key | pass. 10 live models; `run-bdb45fc397b346bd8c2c926009603e8d`, 5 iterations, 47,220 input and 411 output tokens, USD 0.0493 |
| `A25`-`A29` additive group | pass. OAuth and Gemini coexisted as two distinct records with complete catalogs, the CLI printed `Default remains: OpenAI / gpt-5.6-sol` on the Gemini connect and the default was unchanged, `run-7e5f1a3ad9ce47069a9a4b957e456df4` ran explicitly on `gemini-3.5-flash-lite` while OpenAI stayed default, moving the default to Gemini left both catalogs intact, and deleting OpenAI removed exactly one record while Gemini stayed connected and default |
| `BL01`-`BL08` | pass, 8 of 8, recorded in the Part B table |
| `OS-L` | pass, recorded in the installed-product table |
| `D01`-`D07` | pass, 7 of 7, recorded below the Part D table |
| `C01`-`C25` | 21 pass, 4 partial. `C07` to `C09` park correctly and their continuation needs the reply surface that belongs to `0.6.0`. `C21` is partial for `F34`: the raw socket now carries the cancel terminal, and the phone stream cannot until its frozen vocabulary gains a member |
| `E01`-`E05` | pass, 5 of 5, recorded below the Part E table |
| surface coverage | 45 of 47 shipped HTTP rows, all 30 absence probes, 6 of 7 callback rows and 24 of 25 CLI rows pass. The pairing chain is `blocked`, see F32 |

For all four credential paths the key never appeared in the CLI transcript or in
any process argument, sampled continuously during each login; the committed
record's filename matched the opaque `cred_v1_<32 hex>` form; a scan of the
database, WAL and SHM for the exact key value returned zero matches; and the
connection, its catalog and the default survived a restart of the installed
daemon with the record's `sha256` and its `600`/`700` controls unchanged.

`CB04` is closed here independently of the Windows capture: the live browser
approval produced `callback{method=GET path=/auth/callback}: status=303`
followed by `callback{method=GET path=/auth/complete}: status=200`, and a scan
of the whole daemon log for `code=`, `state=` or `access_token` returned zero
matches, verified against the raw file.

## Owner and environment requirements

These requirements are declared before another live group runs. Availability
checks record only present or absent; they never print or persist a secret.

| requirement | cells | non-secret availability check | cost or destructive effect | cleanup |
|---|---|---|---|---|
| billed OpenAI Platform API key | A07-A12, S08c | an OpenAI key is present in the owner-only workspace `.env`; map it in memory to `OPENAI_API_KEY` | provider usage is billed | unset after the isolated group; delete the Vadgr connection |
| billed Gemini API key | A13-A18, S05, S08d | a Gemini key is present in the owner-only workspace `.env`; map it in memory to `GEMINI_API_KEY` | provider usage is billed | unset after the isolated group; delete the Vadgr connection |
| billed Anthropic API key | A19-A24, S08e | an Anthropic key is present in the owner-only workspace `.env`; map it in memory to `ANTHROPIC_API_KEY` | provider usage is billed | unset after the isolated group; delete the Vadgr connection |
| build toolchain on each native host | BL01-BL08, BM01-BM08, BW01-BW08, OS-L, OS-M, OS-W | `cargo --version` answers on that host, and so does its platform C compiler | installs a compiler toolchain, several GB on Windows, whose installer asks for elevation | keep the toolchain; it is host tooling rather than isolated test state |
| native Linux desktop host | BL01-BL08, OS-L | release artifact and installed cua are present on a non-WSL Linux desktop | creates isolated state and reversible test files | remove only the isolated state and test files |
| macOS host | BM01-BM08, OS-M | release artifact and installed cua are present on macOS | creates local Application Support state and reversible test files | remove only the isolated state and test files |
| Windows native host | BW01-BW08, OS-W | release artifact and installed cua are present in native Windows | creates local AppData state and reversible test files | remove only the isolated state and test files |
| WSL2 plus Windows desktop applications | BQ01-BQ08, OS-Q, E01-E05 | installed cua can reach the Windows UI from WSL and Windows Notepad is available | opens one unsaved Notepad scratch document | close only the test document without saving; do not terminate unrelated applications |
| one browser approval and a ten-minute wait | S01 | OpenAI OAuth account is available and callback port `1455` is free | consumes time, not API usage before exchange | close the completion tab and remove the expired attempt |
| permission to replace and delete live provider connections | S04-S05, A25-A29 | owner confirms the isolated state contains no connection that must be retained | rotates/deletes isolated credentials | restore the intended default or remove the isolated state |
| permission to hard-kill the assigned daemon during owner work | E03 | owner confirms the task, reversible effect and assigned daemon PID | interrupts one test daemon during a live call | restart only that daemon and remove the reversible effect |
| authoritative monetary-price source or owner disposition | E04 | provider response, account usage page or approved pricing rule can map usage to money | may require billed-account inspection | record the source and amount, never account secrets |
| permission to exercise installed service lifecycle and update preflight | S12a-S12f | isolated service name, logs and installation root are identified | starts/stops the isolated service; update remains preflight unless explicitly approved | restore the service to its initial state |

Before A07, A13, A19, BL01, BM01, BW01, E03 or E04 starts, report the
corresponding missing item to the owner and wait. No unavailable requirement
may be discovered by silently shrinking the matrix.

## Billed model selection

Selection was rechecked against official provider documentation and the live
catalog on 2026-08-16. The model named below is a candidate only until the
authenticated catalog contains its exact id. An onboarding readiness call uses
the product-selected model once because that choice is part of the shipped user
path. Every repeated provider-neutral engine task then names the cheaper model
explicitly. No fallback runs without a recorded capability failure and a new
cost estimate.

| cells | provider/auth | required capability | explicit engine model | official price checked 2026-08-16 | hard group ceiling | escalation |
|---|---|---|---|---|---|---|
| A01-A06 | OpenAI ChatGPT OAuth | Responses, function calls, multi-turn tool results; image input and image-bearing tool-result continuation for pixel/C12 cells | `gpt-5.6-luna` when the OAuth catalog offers it | [OpenAI model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna): $0.20 input / $1.20 output per MTok; subscription OAuth exposes no attributable API charge | one product-selected readiness plus one explicit run; 6 engine iterations; 100k input; 2k output; no monetary claim | none without a distinct protocol cell |
| A07-A12, S08c | OpenAI Platform API key | Responses, function calls, multi-turn tool results; image input and image-bearing tool-result continuation for pixel/C12 cells | `gpt-5.6-luna` | [OpenAI model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna): $0.20 input / $1.20 output per MTok | one readiness plus one run; 6 iterations; 100k input; 2k output; $0.05 | re-research only if Luna is absent or fails a recorded capability assertion |
| A13-A18, S08d | Gemini API key | `generateContent`, function calls, thought-signature continuation; image input and image-bearing tool-result continuation for pixel/C12 cells | `gemini-3.5-flash-lite` | [Gemini model page](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite): $0.30 input / $2.50 output per MTok | one readiness plus one run; 6 iterations; 100k input; 2k output; $0.05 | re-research only if Flash-Lite is absent or fails a recorded capability assertion |
| A19-A24, S08e | Anthropic API key | Messages, client tools, multi-turn tool results; image input and image-bearing tool-result continuation for pixel/C12 cells | `claude-haiku-4-5-20251001` | [Claude model overview](https://platform.claude.com/docs/en/about-claude/models/overview): $1 input / $5 output per MTok | one readiness plus one run; 6 iterations; 100k input; 2k output; $0.15 | Sonnet only for a prewritten model-specific cell or recorded Haiku capability failure; never Fable or Opus for this generic task |
| A25-A29, S05 | ChatGPT OAuth plus Gemini API key | coexistence, explicit Gemini run, default switch and delete; image input and image-bearing tool-result continuation if the run enters pixel CUA | OAuth product choice once; `gemini-3.5-flash-lite` for the engine run | same OpenAI and Gemini sources above | one OAuth readiness, one Gemini readiness and one Gemini run; 6 engine iterations; 100k input; 2k output; $0.05 attributable API spend | none without a distinct protocol cell |
| E01-E05 | OpenAI Platform API key | multi-turn CUA tool use, Windows UI interaction from WSL, image input and image-bearing tool-result continuation | `gpt-5.6-luna` | [OpenAI model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna), rechecked 2026-08-17: $0.20 input / $1.20 output per MTok | one run; 40 engine iterations; 2M input; 8k output; $0.50 | stop at any ceiling; no model escalation without a written capability failure |

The earlier accepted ChatGPT runs used `gpt-5.6-sol`, and the accepted Gemini
run used `gemini-3.7-flash`, before this policy was added. Their evidence remains
valid, but neither expensive choice is repeated for provider-neutral coverage.
The owner dogfood has a separate ceiling because opening, writing and reading a
native Windows application from WSL requires several grounded UI turns. It is not a
provider-neutral smoke test. Before another billed group runs, its driver must cancel at any ceiling and the
result row must record actual tokens plus calculated cost. A model comparison
adds coverage only when the adapter contract differs; sampling extra models for
its own sake is prohibited.

The cited model pages currently declare image input for Luna, Flash-Lite and
Haiku 4.5. That documentation is not enough by itself: before C12 or any pixel
CUA task, the authenticated catalog must expose the same capability and the
driver must prove that an image tool result reaches the next provider turn. If
either check fails, the visual cell is blocked; a text-only pass cannot replace
it.

## Prerequisites

Use the release artifact and isolate every daemon. Port `1455` must also be
free for the fixed OpenAI browser callback.

```bash
export E2E_ROOT="$(mktemp -d)"
export VADGR_STATE_HOME="$E2E_ROOT/state"
export VADGR_CONFIG_HOME="$E2E_ROOT/config"
export VADGR_DB="$E2E_ROOT/vadgr.db"
export VADGR_RUNS_DIR="$E2E_ROOT/runs"
export VADGR_CUA_BIN=/home/santiago/Santiago/Common/vadgr-computer-use/.venv/bin/vadgr-cua
export VADGR_COMPUTER_USE=true
export VADGR_PORT=9471
export VADGR_TRANSPORT=loopback
export FORGE_API_URL=http://127.0.0.1:9471
mkdir -p "$VADGR_STATE_HOME" "$VADGR_CONFIG_HOME" "$VADGR_RUNS_DIR"
./rust/target/release/vadgr-daemon
```

Before submitting a live run, require `GET /api/computer-use/status` to return
`200` with `available: true`. A fresh database with an inherited user config is
not an isolated test.

Live secrets are entered through the CLI without echo or supplied through the
documented provider environment variable read from the workspace `../.env`.
They are excluded from command arguments, logs, screenshots, transcripts,
process listings, GitHub text, documentation and evidence. Run
`python3 scripts/check_no_secrets.py --env-file ../.env` before each commit and
before every evidence bundle is sealed. The scan reports only paths and rule
names.

## Remote-host handoff for Linux, macOS and Windows

Each native-host Codex session follows this handoff without needing context
from another session:

1. Read `AGENTS.md`, `E2E/README.md` and this runbook completely. Check out the
   same PR head and record `git rev-parse HEAD`. Do not combine results from
   different commits.
2. Place the host's owner-only `.env` one directory above the repository. Use
   `OPENAI_API_KEY`, `GEMINI_API_KEY` and `ANTHROPIC_API_KEY` as the portable
   names. A machine-local alias is allowed, but the driver maps it to the
   portable name only in memory. Check names and presence only. Never print values. Run
   `python3 scripts/check_no_secrets.py --env-file ../.env` before testing. On
   Windows a file created under a work directory inherits broad access entries
   and the gate refuses it. Save the original with `icacls <path> /save
   <backup>`, then strip inheritance with `icacls <path> /inheritance:r
   /grant:r <domain>\<user>:(F)`.
3. Install the build toolchain before anything else: Rust plus that platform's
   C compiler. Rust alone does not build the daemon, because it takes
   `rusqlite` with the `bundled` feature and that compiles SQLite from C
   source. Windows needs Visual Studio Build Tools with the VCTools workload
   and the `x86_64-pc-windows-msvc` target; macOS needs the Xcode command line
   tools; Linux needs `build-essential` or the distribution equivalent. There
   is no prebuilt daemon to download instead. The repository publishes no
   release assets, CI compiles Rust on all three hosts but only in debug and
   uploads no artifact, and released per-OS binaries belong to a later minor.
   Budget the install before reporting a cell as blocked, because a host
   without a toolchain looks blocked for the wrong reason. Then build the
   release with `cargo build --locked --release --manifest-path
   rust/Cargo.toml`. Copy the resulting `vadgr-daemon` or `vadgr-daemon.exe`
   into an empty host-local test root and run that copy. Never use `cargo run`
   as the product under test.
4. Build the exact `vadgr-computer-use` PR-head wheel. Create a fresh Python
   virtual environment inside that test root and install that wheel without
   editable mode. Record its wheel hash and `vadgr-cua doctor`, then set
   `VADGR_CUA_BIN` to that installed executable. On Linux, run
   `vadgr-cua install-deps --yes`. On macOS, grant Accessibility and Screen
   Recording to that environment's Python. On Windows, keep the test native;
   do not route it through WSL.
5. The editor task uses the native application only: GNOME Text Editor on Linux,
   TextEdit on macOS, and Notepad on Windows and WSL. It opens a new unsaved
   scratch document, writes the fixed text, and verifies it through the editor
   UI. It does not open or save a WSL, project, network or other filesystem path.
6. Create the evidence directory before the first cell. Record only the commit,
   artifact hashes, tool versions, redacted commands, status codes, structured
   responses, access-control metadata, journals, socket frames and independent
   read-backs. Do not record environment values, authorization headers, callback
   queries or unredacted screenshots that contain them.
7. Run the platform's eight credential cells in order: `BL01`-`BL08`,
   `BM01`-`BM08` or `BW01`-`BW08`. Then run `OS-L`, `OS-M` or `OS-W`. Preserve
   state only where the next cell names it as a precondition. Use a new state
   root for every unrelated group.
8. Run the secret check again before the evidence boundary is sealed. Remove
   only the isolated state, virtual environment and reversible test effects.
   Do not stop unrelated applications or processes. Update only the rows that
   this host executed, with `pass`, `fail` or `blocked` and the exact reason.

Use these platform-specific isolation variables. Choose a free loopback port
per concurrent pass.

Linux and macOS:

```bash
export E2E_ROOT="$(mktemp -d)"
mkdir -p "$E2E_ROOT/bin" "$E2E_ROOT/state" "$E2E_ROOT/config" "$E2E_ROOT/runs" "$E2E_ROOT/evidence"
install -m 755 rust/target/release/vadgr-daemon "$E2E_ROOT/bin/vadgr-daemon"
python3 -m venv "$E2E_ROOT/cua"
"$E2E_ROOT/cua/bin/python" -m pip install 'vadgr-computer-use==0.7.0'
export VADGR_STATE_HOME="$E2E_ROOT/state"
export VADGR_CONFIG_HOME="$E2E_ROOT/config"
export VADGR_DB="$E2E_ROOT/vadgr.db"
export VADGR_RUNS_DIR="$E2E_ROOT/runs"
export VADGR_CUA_BIN="$E2E_ROOT/cua/bin/vadgr-cua"
export VADGR_COMPUTER_USE=true
export VADGR_PORT=<free-port>
export VADGR_TRANSPORT=loopback
export FORGE_API_URL="http://127.0.0.1:$VADGR_PORT"
"$E2E_ROOT/bin/vadgr-daemon"
```

Native Windows PowerShell:

```powershell
$E2ERoot = Join-Path $env:TEMP ("vadgr-e2e-" + [guid]::NewGuid())
New-Item -ItemType Directory -Force "$E2ERoot\bin", "$E2ERoot\state", `
  "$E2ERoot\config", "$E2ERoot\runs", "$E2ERoot\evidence" | Out-Null
Copy-Item rust\target\release\vadgr-daemon.exe "$E2ERoot\bin\vadgr-daemon.exe"
py -m venv "$E2ERoot\cua"
& "$E2ERoot\cua\Scripts\python.exe" -m pip install vadgr-computer-use==0.7.0
$env:VADGR_STATE_HOME = "$E2ERoot\state"
$env:VADGR_CONFIG_HOME = "$E2ERoot\config"
$env:VADGR_DB = "$E2ERoot\vadgr.db"
$env:VADGR_RUNS_DIR = "$E2ERoot\runs"
$env:VADGR_CUA_BIN = "$E2ERoot\cua\Scripts\vadgr-cua.exe"
$env:VADGR_COMPUTER_USE = "true"
$env:VADGR_PORT = "<free-port>"
$env:VADGR_TRANSPORT = "loopback"
$env:FORGE_API_URL = "http://127.0.0.1:$env:VADGR_PORT"
& "$E2ERoot\bin\vadgr-daemon.exe"
```

## Automated gate (necessary, never sufficient)

| gate | result |
|---|---|
| complete Python suite | pass: 703 passed in 21.32s |
| Rust all-target suite | pass: 178 passed, 1 Docker-only test ignored |
| `cargo fmt --check` | pass |
| `cargo check --all-targets` | pass |
| `cargo clippy --all-targets -- -D warnings` | pass |
| Windows credential module target check | pass |
| macOS credential module target check | pass |
| Linux musl release build | pass: static PIE, SHA-256 `99e4835f3a4607aad9675267401e7030a9355bb44cb004ffc3aac7f31aa813f9` |
| clean install in `scratch` | pass: healthy `0.4.7`, Linux, loopback, cua disabled, three disconnected providers |
| required GitHub Actions jobs | pass: all 12 required jobs green, most recently on `d5e66a3`. `engine`, `api` and `cli` on Python 3.11 and 3.12, `rust` on ubuntu, macOS and windows, `clean-install`, and two `secret-scan` jobs. This row names the head it last ran green on rather than a fixed commit, because every push moves the head and a pinned hash here would read as current while describing an older tree; it is re-read against the branch head at merge. Green here says the suites build and pass on those runners and **nothing** about whether the product works on them |

The automated tests prove deterministic state, protocol, migration, and error
cases. They cannot prove an external account can authenticate, a live model can
act through installed cua, or a killed installed daemon can continue safely.

## Coverage

There are no deferrals from this minor. The `0.4.6` provider-blocked close is
carried here in full and is part of acceptance.

This table is generated from the cells below, never typed. `Verdict` counts a
cell whose result is `pass`, `fail`, `partial` or `Not-Needed`. `Owed` counts
`not run` and `blocked`, both of which are always acceptable and always visible.
`Observation` counts a row whose last column records what a surface returned
rather than a verdict, which is evidence and is deliberately not added to a
completion figure.

| Part | Axes | Cells | Verdict | Owed | Observation |
|---|---|---:|---:|---:|---:|
| Surface coverage | 47 HTTP + 7 callback + 25 CLI + 22 branch cells | 131 | 28 | 1 | 102 |
| A: onboarding | 4 credential paths x 6 assertions + 5 additive/default cells | 29 | 29 | 0 | 0 |
| B: credential storage | 4 platforms x 8 assertions | 32 | 24 | 8 | 0 |
| OS: installed product | 4 operating systems x 1 full live composition | 4 | 3 | 1 | 0 |
| C: engine behavior | 25 carried native-loop cases | 25 | 25 | 0 | 0 |
| D: restart continuation | 1 sequence x 7 assertions | 7 | 7 | 0 | 0 |
| E: owner dogfood | 1 batch x 5 outcomes | 5 | 5 | 0 | 0 |
| Repeatability | 3 independent passes, each reconciled across 6 observables | 3 | 3 | 0 | 0 |
| Findings | corrections recorded during the pass | 34 | 27 | 1 | 6 |
| | | **270** | **151** | **11** | **108** |

Across the whole runbook the verdicts are 145 `pass`, 6 `partial`, 9 `not run`
and 2 `blocked`. F27 and F29 were both found as Windows failures and are now
repaired, so both carry a `pass`; F28 records the one Part D assertion that is
still not demonstrated there. The Part D cells read `pass` in their own table because that
table records the WSL execution, and the Windows execution of the same cells is
recorded in the paragraphs below it and in the per-OS matrix. Every `not run` names the host it needs, and both `blocked`
cells name the product path that does not exist. Run
`python3 <docs>/scripts/check_e2e.py E2E/0.4.7/e2e.md` to reproduce these
numbers from the cells.

`Run` now means executed under the corrected public-entry-point method. The old
numbers are retained only in the private acceptance-diagnostic evidence. Every
surface cell above has a stable id in the tables below.

## Surface coverage - every published endpoint, with what it returned

The corrected sweep at `9761f6a` used direct terminal `curl` for HTTP and the
installed terminal `vadgr` command for CLI rows. Capture-only Node parsers
sanitized and reconciled the returned JSON after each public call; they did not
import or invoke product code. The composed evidence contains all 47 shipped
HTTP rows, all 30 absent-route probes and all 25 CLI rows as passes.

### Shipped

Every row below was captured through direct `curl` against the same isolated
release daemon. Each response was filed immediately. The pass revoked its own
device, cancelled its own runs and stopped only its assigned daemon at cleanup.

| id | endpoint | case | status | code | response, as returned |
|---|---|---|---:|---|---|
| H01 | `POST /api/providers/{provider}/auth-attempts` | valid OAuth cancellation target | `202` | - | pending attempt accepted |
| H02 | `GET /api/provider-auth/{attempt}` | cancelled | `200` | - | attempt state `cancelled` |
| H03 | `GET /api/health` | installed daemon liveness/version | `200` | - | healthy `0.4.7` daemon |
| H04 | `POST /api/auth/pair` | default exists, Tailscale available | `200` | - | one pairing payload |
| H05 | `POST /api/auth/claim` | valid one-time claim | `200` | - | device token and device row |
| H06 | `GET /api/devices` | paired list | `200` | - | claimed device present |
| H07 | `POST /api/auth/claim` | already-used code | `401` | `PAIRING_CODE_INVALID` | named error envelope |
| H08 | `DELETE /api/devices/{device}` | existing device | `200` | - | revoked device row |
| H09 | `POST /api/auth/claim` | invalid code | `401` | `PAIRING_CODE_INVALID` | named error envelope |
| H10 | `GET /api/devices` | after revoke | `200` | - | empty list |
| H11 | `DELETE /api/devices/{device}` | unknown device | `404` | `DEVICE_NOT_FOUND` | named error envelope |
| H12 | `GET /api/providers` | connected default plus disconnected descriptors | `200` | - | OpenAI connected/default; Gemini and Anthropic disconnected |
| H13 | `POST /api/providers/{provider}/auth-attempts` | unknown provider | `400` | `INVALID_PROVIDER_AUTH` | named error envelope |
| H14 | `POST /api/providers/{provider}/auth-attempts` | Gemini rejects OAuth | `400` | `INVALID_PROVIDER_AUTH` | named error envelope |
| H15 | `POST /api/providers/{provider}/auth-attempts` | OpenAI rejects device code | `400` | `INVALID_PROVIDER_AUTH` | named error envelope |
| H16 | `POST /api/providers/{provider}/auth-attempts` | API key omitted | `422` | - | validation envelope |
| H17 | `GET /api/provider-auth/{attempt}` | missing attempt | `404` | `AUTH_ATTEMPT_NOT_FOUND` | named error envelope |
| H18 | `POST /api/providers/{provider}/auth-attempts` | valid OAuth pending target | `202` | - | pending attempt accepted |
| H19 | `GET /api/provider-auth/{attempt}` | pending attempt | `200` | - | attempt state `pending` |
| H20 | `PUT /api/providers/{provider}/connection` | pending attempt | `409` | `AUTH_ATTEMPT_NOT_READY` | connection unchanged |
| H21 | `PUT /api/providers/{provider}/connection` | wrong provider for attempt | `409` | `AUTH_ATTEMPT_NOT_READY` | connection unchanged |
| H22 | `POST /api/providers/{provider}/auth-attempts` | syntactically valid API-key method | `200` | - | bounded validation result recorded |
| H23 | `PUT /api/providers/{provider}/connection` | failed credential validation | `401` | `INVALID_CREDENTIALS` | existing connection preserved |
| H24 | `DELETE /api/providers/{provider}/connection` | provider owns default | `409` | `DEFAULT_MODEL_IN_USE` | connection/default preserved |
| H25 | `DELETE /api/providers/{provider}/connection` | missing disconnected provider | `204` | - | no row created or removed |
| H26 | `POST /api/providers/{provider}/catalog-refresh` | connected live provider | `200` | - | refreshed catalog returned |
| H27 | `POST /api/providers/{provider}/catalog-refresh` | disconnected provider | `409` | `PROVIDER_NOT_CONNECTED` | other rows preserved |
| H28 | `PUT /api/default-model` | valid live readiness | `200` | - | requested default committed |
| H29 | `PUT /api/default-model` | unavailable model | `422` | `MODEL_NOT_AVAILABLE` | old default preserved |
| H30 | `PUT /api/default-model` | disconnected provider | `409` | `PROVIDER_NOT_CONNECTED` | old default preserved |
| H31 | `GET /api/settings/computer-use` | current setting | `200` | - | current value returned |
| H32 | `PUT /api/settings/computer-use` | disable | `200` | - | disabled value committed |
| H33 | `PUT /api/settings/computer-use` | restore | `200` | - | enabled value committed |
| H34 | `GET /api/computer-use/status` | installed cua readiness | `200` | - | available status returned |
| H35 | `GET /api/runs` | populated list | `200` | - | owned runs returned |
| H36 | `POST /api/runs` | default provider/model | `202` | - | run accepted with resolved pair |
| H37 | `POST /api/runs/{run}/cancel` | running run | `200` | - | row moved to cancelled |
| H38 | `GET /api/runs/{run}` | existing run | `200` | - | matching run row |
| H39 | `POST /api/runs` | explicit provider/model | `202` | - | run accepted with explicit pair |
| H40 | `POST /api/runs/{run}/cancel` | second active cleanup | `200` | - | owned run cancelled |
| H41 | `GET /api/runs/{run}` | unknown run | `404` | `RUN_NOT_FOUND` | named error envelope |
| H42 | `POST /api/runs/{run}/cancel` | terminal run | `409` | `RUN_NOT_ACTIVE` | terminal row unchanged |
| H43 | `POST /api/runs/{run}/cancel` | missing run | `404` | `RUN_NOT_FOUND` | named error envelope |
| H44 | `POST /api/runs` | unknown explicit provider | `202` | - | accepted row later failed by engine |
| H45 | `POST /api/runs/{run}/resume` | failed run | `200` | - | same row resumed |
| H46 | `POST /api/runs/{run}/resume` | missing run | `404` | `RUN_NOT_FOUND` | named error envelope |
| H47 | `POST /api/runs/{run}/resume` | completed non-resumable run | `409` | `RUN_NOT_RESUMABLE` | terminal row unchanged |

OAuth callback query values were excluded from evidence. Each callback used a
fresh attempt or an explicitly spent one, captured the response at the route
boundary, then removed its pending state.

| id | endpoint | precondition/action | observed response | status |
|---|---|---|---|---|
| CB01 | `GET /auth/callback?<redacted>` | Owner cancels a pending attempt | `303` to `/auth/failed` | pass on `13074d3`, re-run on WSL after the listener gained tracing. The owner declining in the browser is the provider's `error=access_denied` redirect: a pending attempt presented with it returned `303` to `/auth/failed` and moved to `cancelled` with `auth_cancelled`. An abandoned CLI does not cancel anything, because the daemon never hears it. |
| CB02 | `GET /auth/callback?<redacted>` | Reuse a callback after its attempt is consumed | `303` to `/auth/failed` | pass on `13074d3`: a first callback consumed the attempt, which moved to `failed` with `invalid_credentials`; presenting the same state again returned `303` to `/auth/failed`. |
| CB03 | `GET /auth/callback?<redacted>` | Submit a state that does not match the pending attempt | `303` to `/auth/failed` | pass on `13074d3`: a state matching no pending attempt returned `303` to `/auth/failed`. |
| CB04 | `GET /auth/callback?<redacted>` | Complete a valid live browser authorization | `303` to `/auth/complete` | pass on `e324281`, on native Windows with a live owner approval. The raw status is captured for the first time in this runbook: the daemon log holds `callback{method=GET path=/auth/callback}: status=303` and then `callback{method=GET path=/auth/complete}: status=200`, and the connection committed. It was uncapturable before because the callback listener served its routes with no tracing at all, which is also why the WSL row records the same gap. See F29. The log carries the path only: a scan of the whole daemon log for `code=`, `state=` or any query string returns nothing, verified against the raw file rather than a self-reported flag |
| CB05 | `GET /auth/complete` | Follow CB04 without query parameters | `200`, generic success page | pass on `13074d3`: `200`, generic success page. |
| CB06 | `GET /auth/failed` | Follow a failed callback without query parameters | `400`, generic failure page | pass on `13074d3`: `400`, generic failure page. |
| CB07 | `GET /auth/callback?<redacted>` | Cancel and clean a pending-attempt fixture | `303` to `/auth/failed`; pending state removed | pass on `13074d3`: a pending fixture presented with the provider's error redirect returned `303` to `/auth/failed` and moved to `cancelled`; replaying it was refused with `303` to `/auth/failed`. No provider connection was created by any callback row. |

The real-TTL expiry remains S01 rather than being treated as another CB row.

### The same sweep on native Windows

**Every shipped HTTP row passes here.** The OAuth rows were blocked at first
attempt because the fixed callback port could not be bound, and the cause was
this pass leaking two daemons from its own crashed runs rather than anything in
the product. With them stopped the daemon bound the port and the six OAuth rows
and six of the seven callback rows ran.

Re-recorded on a real Windows 11 host at `dfa80c8` against its own isolated
release daemon, because a sweep that binds sockets, spawns a child process and
resolves a platform credential store does not inherit a WSL result.

| group | Windows result |
|---|---|
| shipped HTTP rows | **47 of 47** match the recorded status and error code |
| absent-route probes | 30 of 30 returned `404` or `405` |
| CLI rows | 25 of 25 returned the expected exit code and nonempty output |
| callback rows | **7 of 7** |

`H01` and `H18` accepted a pending OAuth attempt at `202`, `H02` reported it
`cancelled` after a denial callback, `H19` reported the pending one, and `H20`
and `H21` both refused a commit with `AUTH_ATTEMPT_NOT_READY`.

`CB01`, `CB02` and `CB03` each redirected `303` to `/auth/failed`, for a
cancelled attempt, a reused one and an unissued state. `CB05` served the
query-free completion page at `200` and `CB06` the failure page at `400`, both
generic. `CB07` denied a pending attempt, redirected to `/auth/failed` and left
the attempt `cancelled`.

Three harness faults were corrected here rather than filed as product results,
and each had produced a confident wrong answer. A response body was parsed after
being truncated to 300 characters. The callback routes were probed on the API
port, but they are served by their own listener on the fixed callback port, so
every probe returned `404`. And attempts were "cancelled" through
`DELETE /api/provider-auth/{id}`, **a route that does not exist**, which left the
attempt `pending` and made `H02` and `CB01` silently test the wrong case;
`CB01` then looked like a regression of F7 when it was entirely the harness.
Cancellation is recorded through a denial callback, which is what `CB07` shows.

`H04` to `H11` required the real transport. On loopback the daemon answers
`TRANSPORT_UNREACHABLE` naming `loopback`, which is correct, so the pairing rows
were driven over Tailscale, where the daemon advertised its tailnet name and
bound its tailnet address. The pass claimed one device, proved the one-time code
by reusing it, revoked its own device and confirmed the empty list afterwards.

`K03` is worth naming separately, because it demonstrates the behaviour this
minor exists to deliver, on Windows. From a fresh state `vadgr pair` printed the
provider chooser and **no QR appeared before onboarding**. After one provider
was connected, the same command exited `0` and rendered exactly one QR payload.

Two harness faults were found and corrected while re-recording rather than being
written up as product results. Counting only `stdout` reported six correct
refusals as producing no output when their messages were on `stderr`, which is
where an error belongs. Deciding a fixture's arm from a global call counter
handed a later run the wrong arm once other runs had shifted the parity, which
is the kind of fault that makes a green sweep meaningless.

### Not yet built - probed to confirm absent, not half-wired

The generated sweep reused the 30-route absence inventory from `0.4.6`.
All 30 returned `404` or `405`; no removed route was accepted on the basis of
source inspection.

The common setup was the healthy isolated daemon. Each probe sent the named
method/path, captured status/body immediately, and made no state change.

| id | method and path | observed |
|---|---|---|
| N01 | `GET /api/agents` | `404` |
| N02 | `POST /api/agents` | `404` |
| N03 | `GET /api/agents/no-such-agent` | `404` |
| N04 | `PUT /api/agents/no-such-agent` | `404` |
| N05 | `DELETE /api/agents/no-such-agent` | `404` |
| N06 | `DELETE /api/agents` | `404` |
| N07 | `POST /api/agents/no-such-agent/run` | `404` |
| N08 | `GET /api/agents/no-such-agent/runs` | `404` |
| N09 | `GET /api/agents/no-such-agent/export` | `404` |
| N10 | `POST /api/agents/import` | `404` |
| N11 | `POST /api/agents/no-such-agent/uploads` | `404` |
| N12 | `GET /api/projects` | `404` |
| N13 | `POST /api/projects` | `404` |
| N14 | `GET /api/projects/no-such-project` | `404` |
| N15 | `POST /api/projects/no-such-project/runs` | `404` |
| N16 | `POST /api/projects/no-such-project/validate` | `404` |
| N17 | `DELETE /api/runs` | `405` |
| N18 | `POST /api/runs/held-run/approve` | `404` |
| N19 | `GET /api/runs/held-run/logs` | `404` |
| N20 | `GET /api/runs/held-run/logs/step_01_a.jsonl` | `404` |
| N21 | `GET /api/runs/held-run/outputs/result` | `404` |
| N22 | `GET /api/machine` | `404` |
| N23 | `PATCH /api/machine` | `404` |
| N24 | `POST /api/runs/no-such-run/pause` | `404` |
| N25 | `POST /api/runs/no-such-run/respond` | `404` |
| N26 | `GET /api/runs/no-such-run/journal` | `404` |
| N27 | `POST /api/runs/no-such-run/messages` | `404` |
| N28 | `GET /api/threads` | `404` |
| N29 | `GET /api/approvals` | `404` |
| N30 | `PUT /api/devices/probe/push_token` | `404` |

### The CLI

All commands used the shipped `vadgr` entry point against the isolated daemon.
Every row captured argv, exit, stdout and stderr; empty output was a failure.
Owned background runs were cancelled at the group boundary.

| id | command/case | exit | observed output |
|---|---|---:|---|
| K01 | `vadgr health`, live | `0` | nonempty health/version |
| K02 | `vadgr providers` | `0` | connected and disconnected rows |
| K03 | `vadgr pair`, retained default | `0` | one QR payload |
| K04 | `vadgr run <task> --provider openai --model gpt-5.6-luna --background --json` | `0` | accepted run JSON |
| K05 | `vadgr status` | `0` | isolated service view |
| K06 | `vadgr api --help` | `0` | registered alias help |
| K07 | `vadgr start --help` | `0` | registered command help |
| K08 | `vadgr stop --help` | `0` | registered command help |
| K09 | `vadgr restart --help` | `0` | registered command help |
| K10 | `vadgr logs --help` | `0` | registered command help |
| K11 | `vadgr update --help` | `0` | registered command help |
| K12 | `vadgr computer-use enable` | `0` | enabled setting |
| K13 | `vadgr computer-use disable` | `0` | disabled setting |
| K14 | `vadgr computer-use status` | `0` | installed cua status |
| K15 | `vadgr model list` | `0` | connected catalog union |
| K16 | `vadgr model default openai/gpt-5.6-sol` | `0` | live readiness and committed default |
| K17 | `vadgr provider login gemini --auth chatgpt` | `2` | invalid cross-provider method error |
| K18 | `vadgr provider logout openai` | `1` | default-in-use refusal |
| K19 | `vadgr provider status --refresh openai` | `0` | refreshed OpenAI row |
| K20 | `vadgr runs` | `0` | nonempty run list |
| K21 | `vadgr runs list` | `0` | nonempty run list |
| K22 | `vadgr runs get <completed-run>` | `0` | matching completed row |
| K23 | `vadgr runs cancel <active-run>` | `0` | cancelled row |
| K24 | `vadgr runs resume <completed-run>` | `1` | non-resumable error |
| K25 | `vadgr health`, daemon down | `3` | nonempty unavailable error |

The unexecuted interactive and lifecycle paths are S08a-S12f, not hidden
inside these 25 observed cases.

The former list of 12 branch groups is expanded below into 22 executable cells.
No group begins until its requirement above is available.

| id | precondition and setup | action | expected observable and oracle | evidence boundary | cleanup | status |
|---|---|---|---|---|---|---|
| S01 | Fresh OpenAI OAuth attempt; callback URL held outside evidence; callback port free | Leave consent pending beyond the real ten-minute TTL, then complete or cancel in the browser | Callback redirects to `/auth/failed`; attempt is expired; no connection, staged secret or verifier remains | Callback status/location, attempt row, provider rows, credential filenames, daemon log | Close tab; remove expired attempt | partial on `c990dd2`: public CLI timed out after the real ten-minute TTL; no connection, catalog, default or credential file remained. The later browser approval was rejected upstream, so no daemon callback or `/auth/failed` redirect was observable. |
| S02 | Fresh state with no connection or default | Run `vadgr pair`, complete one passing provider login | Onboarding appears before any QR; readiness passes; exactly one QR is minted afterwards | Complete CLI transcript, auth attempt, provider/default rows, pair response, daemon log | Revoke pair; remove isolated state | pass on `c990dd2`: loopback pairing first showed the provider chooser; after OpenAI OAuth readiness and a Tailscale restart, one QR was minted. Its one-time payload was not retained. |
| S03 | Connected provider whose catalog row is expired through a documented fixture or elapsed TTL | Call `GET /api/providers` and `vadgr provider status` without refreshing | Provider remains connected, reports the catalog stale, and does not fabricate a fresh verification time | HTTP body, CLI output, catalog row before/after | Restore clock/fixture or refresh | pass on `c990dd2`: an isolated catalog expiry fixture made both public surfaces report OpenAI as connected and stale; `verified_at` remained unchanged. |
| S04 | Connected/default OpenAI in isolated state; second OAuth authorization available | Reauthenticate OpenAI and commit the replacement | New immutable reference commits atomically; compatible default/catalog survive; old file leaves only after commit | Before/after provider/default rows, opaque refs, credential filenames, readiness usage | Keep the new isolated connection or remove state | pass on `c990dd2`: a second public OAuth command replaced the opaque reference, removed the old record and preserved `OpenAI / gpt-5.6-sol`. |
| S05 | OpenAI and Gemini connected; OpenAI remains default | Delete Gemini through API and CLI read-back | Gemini credential/catalog leave; OpenAI credential/catalog/default remain byte-for-byte compatible | API response, provider/default rows, filenames, raw DB secret scan | Remove isolated state | pass on `c990dd2`: public Gemini login preserved the OpenAI default; public Gemini logout removed only Gemini while OpenAI and its default remained. |
| S06 | Passing connected provider and captured catalog; upstream then made unreachable without changing local state | Request catalog refresh through API and CLI | Refresh fails with the named error; previous credential, catalog and default remain unchanged | Status/code/body, CLI exit/output, before/after DB rows and filenames | Restore network; refresh once | pass: with the upstream port closed and no local state touched, `POST /api/providers/openai/catalog-refresh` returned `503 PROVIDER_UNAVAILABLE` naming the unreachable URL, and `vadgr model list` still served the captured catalog. The connection, the default and the one catalog row all survived, and `catalog_stale` stayed false. |
| S07 | Two connected providers; captured current default; candidate provider then made unreachable | Request the candidate as default | Readiness fails; old default remains; neither credential nor catalog changes | Status/code/body, before/after default and provider rows | Restore network | pass: with the candidate's upstream closed, `vadgr model default openai/gpt-5-fixture` printed `Checking the model...` then refused with the transport failure. The captured default and the connection were unchanged afterwards. |
| S08a | Fresh state; interactive terminal | Run `vadgr provider login` with no provider argument | Provider chooser shows OpenAI, Gemini, Anthropic once and accepts one selection | TTY transcript and zero provider mutation before selection | Cancel before credentials | pass on `9761f6a`: terminal chooser showed all three providers |
| S08b | OpenAI selected in an interactive terminal | Continue without preselecting a method | Exactly `Continue with ChatGPT` and `OpenAI API key` are offered; cancellation returns without mutation | TTY transcript, provider rows | Cancel and remove attempt | pass on `9761f6a`: both methods appeared once; cancellation left provider JSON byte-identical |
| S08c | Fresh state and owner-supplied OpenAI API key | Complete `vadgr provider login openai --auth api-key` | Hidden entry, live catalog, readiness, immutable credential and successful return; no pairing | CLI transcript without secret, usage, rows, file metadata | Logout and unset key | pass on `9761f6a`: terminal onboarding, live readiness, immutable commit and restart persistence passed |
| S08d | Fresh state and owner-supplied Gemini API key | Complete `vadgr provider login gemini` | No redundant method screen; hidden entry, live catalog/readiness, immutable credential; no pairing | CLI transcript without secret, usage, rows, file metadata | Logout and unset key | pass on `9761f6a`: terminal onboarding, live readiness, immutable commit and restart persistence passed |
| S08e | Fresh state and owner-supplied Anthropic API key | Complete `vadgr provider login anthropic` | No redundant method screen; hidden entry, live catalog/readiness, immutable credential; no pairing | CLI transcript without secret, usage, rows, file metadata | Logout and unset key | pass on `9761f6a`: terminal onboarding, live readiness, immutable commit and restart persistence passed |
| S08f | Interactive login with one deliberately rejected credential followed by a valid owner-supplied credential | Retry through the CLI recovery path | Error is named, input remains hidden, no failed candidate commits, and valid retry succeeds once | CLI exit/output, attempts, rows, filenames before/after | Logout and unset key | partial on `c990dd2`: public terminal invalid-key entry produced the named error and retry menu with zero provider/default mutation. The protected valid-key retry remains open because the automated PTY cannot safely deliver a secret after the interactive recovery prompt. |
| S09 | Fresh state, OpenAI OAuth account, callback port free | Run one uninterrupted `vadgr provider login openai --auth chatgpt` command through browser approval | The same command returns `0` only after readiness and commit; no manual API call completes it | Full CLI transcript, callback redirect, readiness usage, committed rows | Remove isolated state | pass on `9761f6a`: the public command opened the browser, completed readiness and committed the connection before exit `0` |
| S10 | At least two available models; interactive terminal; captured old default | Run `vadgr model default` with no model argument and select a different model | Chooser contains the authenticated union; readiness passes before exactly one default changes | TTY transcript, usage, before/after default | Restore original default | pass on `9761f6a`: 89 authenticated models appeared; Gemini became the sole default after readiness; terminal `vadgr` restored OpenAI |
| S11 | Fresh state with no default | Run `vadgr pair`, choose a provider and authenticate | Successful readiness commits the initial default and continues directly to QR without another question | TTY transcript, usage, rows, pair response | Revoke pair; remove state | pass on `c990dd2`: the S02 fresh state committed the initial OpenAI default before the first QR; the pair command did not ask a second provider or model question. |
| S12a | Installed release; isolated service stopped; known service name | Run `vadgr start` | Service starts on configured port; health is ready; command output names the real endpoint | CLI transcript, process/service record, health, daemon log | Continue to S12b | pass: `vadgr start` on an isolated `AGENT_FORGE_PORT` printed the real endpoint `http://localhost:8477`, the port carried one listener, and health answered `healthy`. **It starts the Python daemon** (`python -m api.serve`), which is the shipped behaviour at this transitional minor; the Rust daemon is started separately and the cutover owns the change. |
| S12b | Service started by S12a | Run `vadgr api` | Alias reaches the same installed daemon and prints nonempty output; it does not start a second daemon | CLI transcript, PID/port snapshot, health | None | pass: with the service already up, `vadgr api` printed `vadgr is already running` and exited `1`, and `vadgr start` exited `1` with the same refusal, so the alias behaves identically. The PID and the single listener on the port were unchanged, so no second daemon started. |
| S12c | Healthy service and active socket capture | Run `vadgr restart` | Old PID exits, port is released, new PID becomes healthy, persisted providers remain | CLI transcript, PID/port snapshots, provider rows, log | Continue to S12d | pass: `vadgr restart` exited `0`; PID 58590 exited, PID 58978 took the port, and health answered `healthy` afterwards. |
| S12d | Healthy restarted service | Run `vadgr logs` | Output is nonempty and belongs to the isolated service instance | CLI transcript and matching daemon-log markers | None | pass, with an independent marker rather than an assumption: a unique request to `/api/runs/s12d-marker-16794` was issued, and `vadgr logs` then contained exactly that line with its `404`, so the output provably belongs to this instance. |
| S12e | Healthy isolated service | Run `vadgr stop` and wait for port release | Command returns only with service stopped or the harness verifies release; health then fails with exit `3` | CLI transcript, service state, port snapshot, health exit/output | Restore initial stopped state | pass: `vadgr stop` exited `0` naming the stopped PID, the port dropped to zero listeners, and `vadgr health` then failed with exit `3` and the not-running message. |
| S12f | Installed release and owner-approved update preflight; no unapproved installation mutation | Run the documented update check or dry-run path | Current/new version and intended artifact are reported; no source-tree execution and no install mutation without explicit approval | CLI transcript, version before/after, filesystem manifest | Restore only if an approved update ran | blocked, and the blocker is the product: **there is no documented update check or dry-run path**. `vadgr update --help` offers no flag, and the command runs `git pull --ff-only origin master` then `pip install` directly. Running it is exactly the unapproved installation mutation this cell forbids, so the cell cannot be executed as written. Recorded as finding F21. |

### The sockets

| socket | frames | types, as received |
|---|---:|---|
| `WS /api/ws/runs/{run_id}` | 8 in A; 5 in B and C | terminal `run_completed` present in all three |
| `WS /api/runs/{run_id}/stream` | 5 in each pass | `started`, `tool_call`, two `output`, `completed` |

## Part A: provider onboarding and defaults

Rows that still cite commits before `9761f6a` are superseded acceptance
observations only. Rows that cite `9761f6a` use the corrected public boundary.

Each credential path has six distinct cells. A readiness-only response does not
close the full-request cell.

| id | precondition and setup | action | expected observable and oracle | evidence boundary | cleanup | status |
|---|---|---|---|---|---|---|
| A01 | Fresh state; callback port free; ChatGPT account available | Start ChatGPT OAuth and approve in the browser | PKCE state matches, query-free completion returns, CLI remains in one flow | CLI transcript, callback status/location, attempt state | Close tab; retain isolated state for A02-A06 | pass on `b753716`: the public CLI flow completed and Windows readback observed `/auth/complete` with an empty query and no `code` or `state` parameters |
| A02 | Passing A01 attempt not yet committed | Let authenticated catalog discovery finish | Account-scoped OpenAI catalog contains seven supported models and no static YAML row | Attempt/catalog response and normalized candidate models | Retain state | pass on `9761f6a`: authenticated catalog returned seven OpenAI models |
| A03 | A02 candidate and starter model | Let bounded readiness run | Direct ChatGPT Responses call returns nonzero usage before commit | Readiness response and usage | Retain state | pass on `9761f6a`: the public command returned success only after live readiness |
| A04 | Passing A03 candidate | Commit the connection | One strict immutable credential file exists; SQLite contains only its opaque reference | Provider/default rows, file metadata, DB/WAL/SHM secret scan | Retain state | pass on `9761f6a`: immutable `0600` record and opaque SQLite reference committed; DB files were token-free |
| A05 | Committed A04 state | Restart daemon and read through API and CLI | OpenAI, seven-model catalog and starter default persist unchanged | Health, API/CLI rows, SQLite rows before/after | Retain state | pass on `9761f6a`: terminal CLI and API preserved the connection, catalog and default after restart |
| A06 | Persisted A05 state with installed cua | Run a goal-level tool-using task through CLI, API, both sockets and journal | Model chooses cua; usage is nonzero; effect is read back; all records reach completed | Run id, journal, raw/mobile frames, API/CLI final rows | Remove reversible effect and isolated state | pass on `9761f6a`: `run-00b9eb0f4655445391f5212c74b2a16b` completed in 3 responses with two matched CUA calls and exact read-back |
| A07 | No existing OpenAI Platform connection; key present | Enter the key without echo through the CLI | Candidate is accepted without key in transcript, argv, logs or process list | Redacted CLI transcript, process snapshot, attempt row | Retain state for A08-A12 | pass on `9761f6a`: public terminal input stayed out of evidence and process arguments |
| A08 | A07 candidate | Discover the Platform catalog | Catalog is authenticated and credential-scoped, with supported capability rows | Attempt/catalog response and rows | Retain state | pass on `9761f6a`: live authenticated catalog returned 51 models |
| A09 | A08 candidate and starter model | Run bounded readiness | Direct OpenAI Platform Responses call returns nonzero usage | Readiness response and usage | Retain state | pass on `9761f6a`: successful public commit requires nonzero readiness usage; exact readiness counts are not exposed |
| A10 | Passing A09 candidate | Commit connection/catalog/default atomically | Strict file and opaque DB reference commit; raw DB files contain no key | Rows, file metadata, DB/WAL/SHM scan | Retain state | pass on `9761f6a`: immutable record and opaque reference committed; raw database scan clean |
| A11 | Committed A10 state | Restart and read through API and CLI | Connection, catalog and default persist without exposing the key | API/CLI and SQLite before/after | Retain state | pass on `9761f6a`: connection, 51-model catalog and default persisted |
| A12 | Persisted A11 state with installed cua | Run one goal-level tool task with a reversible effect | Full native OpenAI API-key adapter, MCP, journal and both streams complete with read-back | Run id, usage, journal, sockets, API/CLI, effect read-back | Delete effect, logout, unset key | pass on `9761f6a`: `run-113d330660434b1695a35cbb793272c0` completed in 4 turns with 3 matched calls and exact read-back |
| A13 | No existing Gemini connection; key present | Enter the key without echo through the CLI | Candidate is accepted with no redundant auth-method question and no secret exposure | Redacted CLI transcript, process snapshot, attempt row | Retain state for A14-A18 | pass on `9761f6a`: public terminal input stayed out of evidence and process arguments |
| A14 | A13 candidate | Discover Gemini catalog | Authenticated Gemini catalog and capabilities are normalized without static YAML | Attempt/catalog response and rows | Retain state | pass on `9761f6a`: live authenticated catalog returned 28 models |
| A15 | A14 candidate and starter model | Run bounded readiness | Direct `generateContent` call returns nonzero usage | Readiness response and usage | Retain state | pass on `9761f6a`: successful public commit requires nonzero readiness usage; exact readiness counts are not exposed |
| A16 | Passing A15 candidate | Commit connection/catalog/default atomically | Strict file and opaque DB reference commit; raw DB files contain no key | Rows, file metadata, DB/WAL/SHM scan | Retain state | pass on `9761f6a`: immutable record and opaque reference committed; raw database scan clean |
| A17 | Committed A16 state | Restart and read through API and CLI | Gemini connection, catalog and default persist without exposing the key | API/CLI and SQLite before/after | Retain state | pass on `9761f6a`: connection and 28-model catalog persisted while OpenAI stayed default |
| A18 | Persisted A17 state with installed cua | Run one goal-level tool task with a reversible effect | Full Gemini adapter, MCP, journal and both streams complete with read-back | Run id, usage, journal, sockets, API/CLI, effect read-back | Delete effect, logout, unset key | pass on `9761f6a`: bounded `run-19fa499edbf94542b5d7b4321447d597` completed in 2 turns with exact read-back |
| A19 | No existing Anthropic connection; key present | Enter the key without echo through the CLI | Candidate is accepted with no redundant auth-method question and no secret exposure | Redacted CLI transcript, process snapshot, attempt row | Retain state for A20-A24 | pass on `9761f6a`: public terminal input stayed out of evidence and process arguments |
| A20 | A19 candidate | Discover Anthropic catalog | Authenticated Anthropic catalog and capabilities are normalized without static YAML | Attempt/catalog response and rows | Retain state | pass on `9761f6a`: live authenticated catalog returned 10 models |
| A21 | A20 candidate and starter model | Run bounded readiness | Direct Messages call returns nonzero usage | Readiness response and usage | Retain state | pass on `9761f6a`: successful public commit requires nonzero readiness usage; exact readiness counts are not exposed |
| A22 | Passing A21 candidate | Commit connection/catalog/default atomically | Strict file and opaque DB reference commit; raw DB files contain no key | Rows, file metadata, DB/WAL/SHM scan | Retain state | pass on `9761f6a`: immutable record and opaque reference committed; raw database scan clean |
| A23 | Committed A22 state | Restart and read through API and CLI | Anthropic connection, catalog and default persist without exposing the key | API/CLI and SQLite before/after | Retain state | pass on `9761f6a`: connection and 10-model catalog persisted while OpenAI stayed default |
| A24 | Persisted A23 state with installed cua | Run one goal-level tool task with a reversible effect | Full Anthropic adapter, MCP, journal and both streams complete with read-back | Run id, usage, journal, sockets, API/CLI, effect read-back | Delete effect, logout, unset key | pass on `9761f6a`: `run-fd1af6af9bc6441393b3c0ff6c969655` completed in 2 turns with exact read-back |
| A25 | Fresh state; OpenAI OAuth and Gemini key available | Connect OpenAI, then Gemini in one isolated state | Both credential files and complete catalogs coexist | Provider/default rows, filenames and DB secret scan after each commit | Retain state for A26-A29 | pass on `c990dd2`: public OAuth then hidden Gemini-key login committed both isolated credential records and complete catalogs. |
| A26 | A25 with OpenAI default | Read providers/default after Gemini commit | OpenAI default remains exactly unchanged | Before/after default and catalog rows | Retain state | pass on `c990dd2`: the default remained OpenAI after Gemini catalog commit. |
| A27 | A26 with installed cua | Run explicitly through a Gemini model | Gemini run completes with read-back while OpenAI remains default | Run/journal/sockets and default before/after | Delete effect; retain state | pass on `c990dd2`: `run-b3a91597d63c4712b825950b9715b49c` completed on `gemini-3.5-flash-lite` with exact file read-back and OpenAI still default. |
| A28 | Passing A27 state | Set a Gemini model as default | Readiness passes, then one atomic default change commits; both catalogs remain | Usage and rows before/after | Retain state | pass on `c990dd2`: public `vadgr model default gemini/gemini-3.5-flash-lite` committed one Gemini default. |
| A29 | A28 with OpenAI now non-default | Delete OpenAI connection | Only OpenAI credential/catalog leave; Gemini connection/default survive | API/CLI response, rows, filenames, DB secret scan | Remove isolated state; unset key | pass on `c990dd2`: public OpenAI logout removed only OpenAI while Gemini remained the default. |

**The same three credential paths on native Windows.** Re-run at `dfa80c8` on a
real Windows 11 host, because a credential path resolves a platform store and
does not inherit a WSL result. Every row below is the product's own output.

| cells | provider and model | live catalog | run | usage | effect |
|---|---|---:|---|---|---|
| A07-A12 | OpenAI Platform API key, `gpt-5.6-luna` | 51 models | `run-eef39f21052949f08ce0028ec9d0d846`, 4 responses | 23,073 input, 311 output, USD 0.0050 | exact marker read back |
| A13-A18 | Gemini API key, `gemini-3.5-flash-lite` | 28 models | `run-2b73def698f74206832ae2660a44b24b`, 3 responses | 23,898 input, 370 output, USD 0.0081 | exact marker read back |
| A19-A24 | Anthropic API key, `claude-haiku-4-5-20251001` | 10 models | `run-2cc2a8933d3b4376b4bd9d055bb1b2d0`, 3 responses | 28,598 input, 530 output, USD 0.0313 | exact marker read back |

**The OAuth path and the additive group on the same host.** One owner browser
approval closed `S09` and `A01` to `A06`: `vadgr provider login openai --auth
chatgpt` returned `0` after 12.4 seconds, having opened the browser, completed
readiness and committed, with a seven model account-scoped catalog, an opaque
record under a protected DACL, and a connection that survived a restart.

`A25` to `A29` then ran in one isolated state. OpenAI connected by OAuth with
seven models and Gemini by API key with twenty eight, as two distinct records.
The CLI printed `Default remains: OpenAI / gpt-5.6-sol` on the Gemini connect,
and the default was byte-identical before and after. An explicit Gemini run,
`run-9a5b7604444e49e08ca7c64dbd8d70f6` on `gemini-3.5-flash-lite`, completed in
three responses with an exact read-back while OpenAI stayed default. Moving the
default to Gemini left both catalogs intact, and deleting OpenAI removed exactly
one record while Gemini stayed connected and default.

Each path stayed inside its written ceiling of six engine iterations, 100k
input and 2k output. For all three the key never appeared in argv or in command
output, the committed record's filename matched the opaque `cred_v1_<32 hex>`
form, a scan of the database, WAL and SHM for the exact key value returned zero
matches, and the connection and its catalog survived a restart of the installed
daemon.

**Measured Gemini close.** Run
`run-06d3f88bf81b4441acd0d6f34df02b89` used `gemini-3.7-flash`, completed in
three iterations, and reported 23,978 input plus 166 output tokens. The journal
contains three provider responses and two matched `in_flight`/`done` installed
CUA calls with no error. Raw and mobile streams both reached their completed
terminal frame, the exact file content matched independent read-back, and the
provider/catalog/default survived a daemon restart. The credential was a
regular owner-owned `0600` record in a `0700` directory behind an opaque
reference; its value was absent from SQLite, WAL, SHM and evidence.

## Part B: credential storage and migration

The WSL statuses in this section are superseded acceptance observations. The
E2E status of every B cell remains `not run` under the corrected method.

Each supported platform executes all eight cases. Platform ids are `BL` native
Linux, `BM` macOS, `BW` Windows native and `BQ` WSL.

| case | precondition and setup | action | expected observable and oracle | evidence boundary | cleanup |
|---|---|---|---|---|---|
| 01 | Fresh isolated state root and absent database | Start the installed daemon | Migration one and null singleton default commit atomically; health serves only after migration | Daemon log, schema/user version, tables, health/providers | Stop daemon; retain state for inspection |
| 02 | Real copied `0.4.6` database with known historical run; fresh credential root | Start the installed `0.4.7` daemon | Historical run remains readable; migration reaches one; no legacy credential is imported | Source hash, migrated schema, run/API read-back, provider rows | Remove isolated copy only |
| 03 | Local fake provider and three unique sentinel secrets | Create, resolve, rotate and delete records for all three providers | Connections coexist; rotation changes only one opaque ref; resolution returns exact sentinel; DB/WAL/SHM contain none; delete affects one | Operation results, rows, filenames, hashes, raw DB secret scan | Delete isolated records/state |
| 04 | One valid committed record | Inspect schema, filename, owner and access controls without printing secret | Strict version 1 JSON, no unknown fields, opaque immutable ref, regular file and platform owner-only controls | Redacted metadata, stat/ACL/DACL, reference row | Retain state for 05-08 |
| 05 | Valid owner-only state plus isolated copies with one control weakened at a time | Start/resolve under correct owner, broad access, wrong mode/ACL and wrong owner | Positive control passes; every weakened effective control fails closed by name | Per-case exit/log, effective ACL/DACL and owner metadata | Restore/remove isolated copies |
| 06 | Isolated fixtures for malformed, oversized, mismatched, linked and unsafe records/roots | Start or resolve each fixture; on WSL also use real drvfs without enforceable modes | Malformed JSON/ref, size, provider/version/field mismatch, symlink/reparse, unsafe owner/access and unenforceable filesystem all fail closed; valid control passes | Named-case matrix, exit/log, path metadata | Remove fixtures without following links |
| 07 | Old committed reference plus staged new file; fault injected before SQLite commit | Restart installed daemon | Staged orphan is removed and old committed reference remains readable | Files and provider rows before/after restart, cleanup log | Remove isolated state |
| 08 | New reference committed; old file deliberately left; fault injected after SQLite commit | Restart installed daemon | New committed reference survives and resolves; old orphan is removed | Files and provider rows before/after restart, cleanup log | Remove isolated state |

| id | platform | case | result |
|---|---|---:|---|
| BL01 | native Linux | 01 | pass on `14b995b`: the database was absent before start. The daemon log orders the assertion rather than assuming it: recovery and the listener are logged at `19:37:05.481`, and the first health `200` at `.527`, so health served only after migration. `user_version` reached 1 with `devices`, `machine_settings`, `provider_catalogs`, `provider_connections`, `provider_models` and `runs`. `machine_settings` held exactly one row with `default_provider` and `default_model` both null, which is the null singleton default. All three providers reported disconnected with empty catalogs, health reported `platform: linux`, and the installed `vadgr health` agreed at exit `0`. |
| BL02 | native Linux | 02 | pass on `14b995b`: the fixture is a real `0.4.6` database produced by the `0.4.6` release binary built from tag `v0.4.6` on this host, which reported `version: 0.4.6` and created `user_version` 0 with only `devices` and `runs`. That daemon wrote a genuine historical run `run-3c7954f347ac4bd99e7dbb54e8d758d1` through `POST /api/runs`, which reached the terminal `failed` state through the legacy provider path. The database was copied through the SQLite backup API, `sha256 424d761a`, carrying one run row. The installed `0.4.7` daemon migrated it to `user_version` 1 and added `machine_settings`, `provider_catalogs`, `provider_connections` and `provider_models`. The historical run stayed readable on both public surfaces: `GET /api/runs/<id>` returned `200` with its exact title and status, and `vadgr runs list` printed it at exit `0`. No legacy credential was imported: the credential root held zero files at mode `0700`, `provider_connections` held zero rows, and all three providers reported `connected: false`. |
| BL03 | native Linux | 03 | pass on `14b995b`: a local stand-in provider served all three catalog and completion routes through the daemon's documented endpoint configuration, and the public `vadgr provider login` connected OpenAI, Gemini and Anthropic with three unique sentinels, each at exit `0`. OpenAI needed `--auth api-key` because it is the only provider offering two methods. All three coexisted, each holding a distinct opaque `cred_v1_<32 hex>.json` reference, each file `0600` inside a `0700` directory. Resolution returned the exact sentinel: the stand-in received the matching `sha256` for each provider on both its catalog and its completion route. Rotating OpenAI moved only that reference, from `02faa90d` to `1b8f44fd`, deleted the old file and left the Gemini and Anthropic references untouched. The public `vadgr provider logout gemini` exited `0` and removed only Gemini's connection, record and catalog, while OpenAI stayed connected and default and Anthropic stayed connected. The database, WAL and SHM held zero sentinel matches at every stage. |
| BL04 | native Linux | 04 | pass on `14b995b`: every committed record is a strict version 1 JSON object with exactly the allowed keys, so no unknown field survives. An API-key record carries `version`, `provider`, `kind: api_key` and `api_key`; the OAuth record committed in `A04` carries `version`, `provider`, `kind: oauth`, `access_token`, `refresh_token` and `expires_at`. Each filename matches the opaque `cred_v1_<32 hex>.json` form, each reference stored in `provider_connections` resolves to a real file, and every record is a regular file at mode `600` with one hard link, owned by the running uid, inside a `700` directory of the same owner. `getfacl` shows only the three base entries with no extended ACL, and `getfattr` reports no extended attribute. No secret value was printed at any point; presence was asserted by a boolean and identity by a `sha256`. |
| BL05 | native Linux | 05 | pass on `14b995b`: six controls were driven, each on its own isolated copy with exactly one weakening, and every one failed closed by name. The positive control refreshed at `200`. A credential record at `0644` and at `0640` each produced `credential path mode must be 600`. A credential directory at `0755` stopped the daemon before it served at all, with `credential path mode must be 700`. An access ACL added with `setfacl` while the mode bits were restored to `0600` produced `credential path has an extended access ACL`, which is the ACL check firing on its own rather than the mode check catching the mask. A record owned by uid 0 while the daemon ran as uid 1000 produced `credential path <path> is owned by uid 0, not by uid 1000`, so the refusal names the path and both ids. Every refusal arrived as `PROVIDER_UNAVAILABLE` with category `credential_store_failed`. The root-owned isolated copy was removed afterwards. |
| BL06 | native Linux | 06 | pass on `14b995b`: nine unsafe fixtures were each staged on an isolated copy and driven through the public refresh, and every one failed closed with its own name, while the valid control resolved at `200` with its catalog. Malformed record JSON gave a parse position; a malformed reference gave `credential reference is malformed`; a 70 KB record gave `credential record exceeds 64 KiB`; a record naming `gemini` under the OpenAI connection gave `credential provider does not match its connection`; `version: 2` gave `unsupported credential record version 2`; an added field gave ``unknown field `extra` `` listing the three it accepts; a record replaced by a symlink gave `credential path has an unsafe type`; a credential directory replaced by a symlink stopped the daemon with `credential directory is not a regular directory`. The Linux specific case is the filesystem that cannot enforce a mode, which is this platform's counterpart of the WSL drvfs row: an isolated state was placed on a loopback FAT16 mount, where `chmod 0700` is silently a no-op and the mode stays `777`, and the daemon refused to serve at all with `credential path mode must be 700`. The FAT fixture was unmounted and removed afterwards. |
| BL07 | native Linux | 07 | pass on `14b995b`: a staged temporary record named `.cred_stage_<32 hex>.tmp` was left beside two committed records, with the database still naming only the two committed references, which is the shape a fault before the SQLite commit leaves behind. On restart the daemon removed the staged orphan and kept both committed records: the directory listing afterwards held exactly the two `cred_v1_` files, and the public refresh resolved at `200` with OpenAI connected and default and Anthropic connected. |
| BL08 | native Linux | 08 | pass on `14b995b`: an extra committed-looking record `cred_v1_cdcd...cd.json` was left in the directory while the database named only the two current references, which is the shape a fault after the SQLite commit leaves behind. On restart the daemon removed the unreferenced record and kept both named ones, and the public refresh resolved at `200`, so the committed reference survived and still resolved. |
| BM01 | macOS | 01 | not run: host required |
| BM02 | macOS | 02 | not run: host required |
| BM03 | macOS | 03 | not run: host required |
| BM04 | macOS | 04 | not run: host required |
| BM05 | macOS | 05 | not run: host required |
| BM06 | macOS | 06 | not run: host required |
| BM07 | macOS | 07 | not run: host required |
| BM08 | macOS | 08 | not run: host required |
| BW01 | Windows native | 01 | pass on `dfa80c8`: the database was absent before start, and the daemon log orders the assertion rather than assuming it. Recovery completed at `07:20:46.423`, the listener opened at `.424`, and the first health `200` arrived at `.926`, so health served only after migration. `user_version` reached 1 with `devices`, `machine_settings`, `provider_catalogs`, `provider_connections`, `provider_models` and `runs`. `machine_settings` held exactly one row with `default_provider` and `default_model` both null, which is the null singleton default. All three providers reported disconnected with empty catalogs, health reported `platform: windows`, and the installed `vadgr health` agreed at exit `0`. |
| BW02 | Windows native | 02 | pass on `dfa80c8`: the fixture is a real `0.4.6` database produced by the `0.4.6` release binary itself, which reported `version: 0.4.6` on Windows and created `user_version` 0 with only `devices` and `runs`. That daemon wrote a genuine historical run `run-196167e196be47a3ba2c79e61d191c63` through `POST /api/runs`, which reached a terminal state through the legacy provider path. The database was copied through the SQLite backup API, `sha256 3389ad2a`, carrying one run row. The installed `0.4.7` daemon migrated it to `user_version` 1 and added `machine_settings`, `provider_catalogs`, `provider_connections` and `provider_models`. The historical run stayed readable on both public surfaces: `GET /api/runs/<id>` returned `200` and `vadgr runs list` exited `0`. No legacy credential was imported: the credential root held zero files and all three providers reported `connected: false`. |
| BW03 | Windows native | 03 | pass on `dfa80c8`: a local stand-in provider served all three catalog and completion routes through the daemon's documented endpoint configuration, and the public `vadgr provider login` connected OpenAI, Gemini and Anthropic with three unique sentinels, each at exit `0`. OpenAI needed `--auth api-key` because it is the only provider offering two methods. All three coexisted, each holding a distinct opaque `cred_v1_<32 hex>.json` reference. Resolution returned the exact sentinel: the stand-in received the matching `sha256` for each provider on both its catalog and its completion route. Rotating OpenAI moved only that reference, from `6a5e589c` to `cee78c1a`, deleted the old file and left the Gemini and Anthropic references untouched. The public `vadgr provider logout gemini` exited `0` and removed only Gemini's connection, record and catalog, while OpenAI stayed connected and default and Anthropic stayed connected. The database, WAL and SHM held zero sentinel matches at every stage. |
| BW04 | Windows native | 04 | pass on `dfa80c8`: every committed record is a strict version 1 JSON object with `kind: api_key` and exactly the four allowed keys, so no unknown field survives. Each filename matches the opaque `cred_v1_<32 hex>.json` form, each reference resolves to a real file, and every record is a regular file rather than a symlink. The Windows access control is the platform-specific half and it holds: the credential directory and each record both carry a **protected** DACL, so nothing is inherited, with exactly two allow entries, `OWNER RIGHTS` and `NT AUTHORITY\SYSTEM`, both full control and both non-inherited, owned by the running account. That is the `D:P(A;;FA;;;SY)(A;;FA;;;OW)` descriptor the store applies, observed on a real Windows host for the first time. No secret value was printed: presence was asserted by a boolean and identity by a `sha256`. |
| BW05 | Windows native | 05 | pass on `dfa80c8`: seven controls were driven, each on its own freshly built state so the descriptor under test is the one the product wrote, and each with exactly one weakening. The positive control refreshed at `200`. An extra ACE granting Users read on the record gave `credential DACL grants unexpected principals`. Re-enabling inheritance gave `credential DACL inherits access`, which is the protection flag firing on its own rather than the ACE count catching it. Reducing owner rights from full control to read gave `credential DACL is not owner-only`, so the access mask is checked and not just the principal. Replacing owner rights with Users gave `credential DACL grants unexpected principals`. An extra ACE on the credential directory stopped the daemon before it served at all. The wrong-owner control was staged by an elevated helper, which is what it needs, and it also fails closed: handing the record to the Administrators group produced `credential store failed: Access is denied. (os error 5)`. That refusal is correct but generic rather than the store's own owner message, because the protected DACL grants through `OWNER RIGHTS`, so moving the owner revokes the running account's access before the owner comparison can run. Every refusal arrived as `PROVIDER_UNAVAILABLE` with category `credential_store_failed`. |
| BW06 | Windows native | 06 | pass on `dfa80c8`: eight fixtures were each staged on their own state and driven through the public refresh, and every one failed closed with its own name while the valid control resolved. Malformed record JSON gave a parse position. A 70 KB record gave `credential record exceeds 64 KiB`. A record naming a different provider than its connection gave `credential provider does not match its connection`. `version: 2` gave `unsupported credential record version 2`. An added field gave ``unknown field `extra` `` with the three it accepts listed. A reference replaced in SQLite gave `credential reference is malformed`. A record replaced by a real symlink, staged by an elevated helper, gave `credential path has an unsafe type`. The Windows specific case is the reparse point, which no other platform produces the same way: the credential directory was replaced by a junction, and the daemon refused to serve at all with `credential directory is not a regular directory`. |
| BW07 | Windows native | 07 | pass on `dfa80c8`: a staged temporary `.cred_stage_<32 hex>.tmp` was left beside two committed records while the database still named only the two committed references, which is the shape a fault before the SQLite commit leaves. On restart the daemon removed the staged orphan and kept both committed records, the directory listing afterwards held exactly the two `cred_v1_` files, and the public refresh resolved at `200`. |
| BW08 | Windows native | 08 | pass on `dfa80c8`: an extra committed-looking record `cred_v1_cdcd...cd.json` was left in the directory while the database named only the two current references, which is the shape a fault after the SQLite commit leaves. On restart the daemon removed the unreferenced record and kept both named ones, and the public refresh resolved at `200`, so the committed reference survived and still resolved. |
| BQ01 | WSL | 01 | pass on `c990dd2`: public CLI and direct health API agreed on a fresh schema-v1 database with no provider, catalog or default rows. |
| BQ02 | WSL | 02 | pass on `ed99bdb`: a real `0.4.6` database copied by the SQLite backup API, `sha256 11a079c0`, started at `user_version` 0 with only `devices` and `runs`. The installed `0.4.7` daemon migrated it to `user_version` 1 and added `machine_settings`, `provider_catalogs`, `provider_connections` and `provider_models`. The historical run `run-715acf93349147deb2254e2f99a74cef` stayed readable on both public surfaces: `GET /api/runs/<id>` returned 200 with its exact title, model, timestamps and outputs, and `vadgr runs list` printed it. No legacy credential was imported: the fresh credential root stayed empty at mode `0700`, `provider_connections` held zero rows, and all three providers reported `connected: false`, although the run row carries the legacy `anthropic_oauth` provider value. |
| BQ03 | WSL | 03 | pass on `ed99bdb`: a local stand-in provider served all three catalogs and completion routes, and the public `vadgr provider login` connected OpenAI, Gemini and Anthropic with three unique sentinels. All three coexisted, each holding a distinct opaque `cred_v1_<32 hex>.json` reference, each file `0600` inside a `0700` directory. Resolution returned the exact sentinel: the stand-in received a matching `sha256` for each provider on both its catalog and its completion route. Rotating OpenAI moved only that reference from `998727fc` to `643f3229`, deleted the old file, and left the Gemini and Anthropic references untouched. The public `vadgr provider logout gemini` removed only Gemini's connection row, credential file and catalog rows, while OpenAI stayed connected and default and Anthropic stayed connected. The database, WAL and SHM held zero sentinel matches at every stage. |
| BQ04 | WSL | 04 | pass on `ed99bdb`: both committed records are strict version 1 JSON objects with `kind: api_key` and exactly the four allowed keys, so no unknown field survives the `deny_unknown_fields` record shape. Each filename matches the opaque `cred_v1_<32 hex>.json` form and each reference stored in `provider_connections` resolves to a real file. Every record is a regular file at mode `600` with one hard link, owned by the running uid, inside a `700` directory of the same owner. `getfacl` shows only the three base entries with no extended ACL, and no extended attribute is set. No secret value was printed at any point; presence was asserted by a boolean. |
| BQ05 | WSL | 05 | pass on `ed99bdb`: all six controls were driven, each on its own isolated copy with exactly one weakening, and every one failed closed by name. The positive control resolved and listed both catalogs. A credential file at `0644` and at `0640` each produced `credential path mode must be 600`. A credential directory at `0755` stopped the daemon before it served, with `credential path mode must be 700`. An access ACL added while the mode bits were restored to `0600` produced `credential path has an extended access ACL`, which is the ACL check firing on its own rather than the mode check catching the mask. A record owned by uid 0 while the daemon ran as uid 1000 produced `credential path <path> is owned by uid 0, not by uid 1000`, so the refusal names the path and both ids as the code intends. The root-owned isolated copy was removed afterwards. |
| BQ06 | WSL | 06 | pass on `ed99bdb`: nine unsafe fixtures were each staged on an isolated copy and driven through the public refresh, and every one failed closed with its own name, while the valid control resolved. Malformed record JSON gave a parse position; a malformed reference gave `credential reference is malformed`; a 70 KB record gave `credential record exceeds 64 KiB`; a record naming `gemini` under the OpenAI connection gave `credential provider does not match its connection`; `version: 2` gave `unsupported credential record version 2`; an added field gave `unknown field: extra`, listing the three it accepts; a record replaced by a symlink gave `credential path has an unsafe type`; a credential directory replaced by a symlink stopped the daemon with `credential directory is not a regular directory`. The WSL specific case ran on a real `drvfs` mount, where `chmod 0700` is silently a no-op and the mode stays `777`: the daemon refused to serve at all, with `credential path mode must be 700`. The drvfs fixture was removed afterwards. |
| BQ07 | WSL | 07 | pass on `ed99bdb`: a staged temporary record named `.cred_stage_<32 hex>.tmp` was left beside two committed records, with the database still naming only the two old references, which is the shape a fault before the SQLite commit leaves behind. On restart the daemon removed the staged orphan and kept both committed records: the directory listing afterwards held exactly the two `cred_v1_` files, and the public refresh resolved OpenAI as connected and default and Anthropic as connected. |
| BQ08 | WSL | 08 | pass on `ed99bdb`: an extra committed-looking record `cred_v1_cdcd...cd.json` was left in the directory while the database named only the two current references, which is the shape a fault after the SQLite commit leaves behind. On restart the daemon removed the unreferenced record and kept both named ones: the directory listing afterwards held exactly the two referenced files, and the public refresh resolved OpenAI as connected and default and Anthropic as connected, so the committed reference survived and still resolved. |

## Installed product on every supported operating system

The earlier OS-Q row is a superseded acceptance observation. The corrected E2E
status of every OS cell is `not run`.

These cells use a release artifact installed on that host, a real supported
provider connection and the installed cua child. Compilation or a fake-provider
credential matrix cannot substitute for them.

| id | precondition and setup | goal | expected observable and oracle | evidence boundary | cleanup | status |
|---|---|---|---|---|---|---|
| OS-L | Native Linux desktop; installed release and cua; fresh state; one owner-supplied provider credential; the documented native text editor is available | Inspect the native OS/session. Open the native text editor, enter the fixed scratch text in an unsaved document, inspect it through the editor UI, restart Vadgr and confirm provider persistence | Health says Linux; real model usage is nonzero; installed cua performs and reads the editor UI effect; journal/API/CLI/both sockets agree; credential controls survive restart | Artifact hash, install command, provider rows, run id/journal/frames, editor UI read-back, restart rows | Close only the test unsaved document without saving; remove isolated state | pass on `14b995b`: `run-10ef6e9ae15e4a33ae5f69f14e1b4895` completed on `gpt-5.6-luna` in 13 model responses, under the 40 ceiling, using 145,651 input and 763 output tokens. The host is Ubuntu 26.04 on a GNOME Wayland session. Health reported `platform: linux` with `computer_use: true`, and `GET /api/computer-use/status` returned `available: true` with `platform: native` before the run was submitted. The catalog was authenticated and live at 51 models and contained the exact selected id. The journal records the real desktop sequence through the installed cua, and it is a structured-tier sequence rather than a pixel one: `apps`, `app_open org.gnome.TextEditor.desktop`, `ui_tree`, `ui_act click`, `ui_tree`, then `ui_act set_text` of exactly `Vadgr dogfood\nVerified through editor UI`, a `screenshot`, and a final `ui_tree` as the UI read-back. `get_platform_info` reported the AT-SPI backend reachable and enabled with `coordinate_trust: per_window`, which is the Wayland answer. No filesystem tool was called at all, so nothing was opened, created or saved. Independent oracle, captured outside both vadgr and cua: GNOME Text Editor's own draft in its private state directory holds exactly `Vadgr dogfood\nVerified through editor UI` plus the editor's trailing newline, 41 bytes, which reconciles with the 40 characters the run typed. After stopping only the assigned pid and restarting the same state, OpenAI stayed connected and default, the providers payload was byte-identical, the credential record's `sha256` and its `600`/`700` controls were unchanged, and the run row still served `200`. The isolated draft was removed at cleanup. |
| OS-M | macOS desktop; installed release and cua; fresh state; one owner-supplied provider credential; TextEdit is available | Inspect macOS/session. Open TextEdit, enter the fixed scratch text in an unsaved document, inspect it through the editor UI, restart Vadgr and confirm provider persistence | Health says macOS; live provider and installed cua complete; journal/API/CLI/sockets and editor UI read-back agree; local Application Support controls survive | Same artifacts as OS-L plus macOS ACL/owner metadata | Close only the test unsaved document without saving; remove isolated state | not run: macOS host required |
| OS-W | Native Windows desktop; installed release and cua; fresh state; one owner-supplied provider credential; Notepad is available | Inspect Windows/session. Open Notepad, enter the fixed scratch text in an unsaved document, inspect it through the editor UI, restart Vadgr and confirm provider persistence | Health says Windows; live provider and installed cua complete; journal/API/CLI/sockets and editor UI read-back agree; AppData DACL survives | Same artifacts as OS-L plus Windows DACL/reparse metadata | Close only the test unsaved document without saving; remove isolated state | pass on `dfa80c8`: `run-359be04d96414c609f35989fbb151fd5` completed on `gpt-5.6-luna` in 15 model responses, under the 40 ceiling, using 126,926 input and 676 output tokens. Health reported `platform: windows` with `computer_use: true`, and `GET /api/computer-use/status` returned `available: true` with `platform: native` before the run was submitted. The catalog was authenticated and live at 51 models and contained the exact selected id. The journal records the real desktop sequence through the installed cua: `apps`, `ui_windows`, screenshot, click, screenshot, click, `type_text Notepad`, screenshot, `enter`, screenshot, click, then `type_text` of exactly `Vadgr dogfood\nVerified through editor UI`, then a final screenshot as the UI read-back. No filesystem tool was called at all, so nothing was opened, created or saved. Independent oracle, captured outside both vadgr and cua: the Notepad window holds exactly those two lines, carries the unsaved marker on its tab, and its own status bar reads `Ln 2, Col 27` and `40 characters`, which reconciles exactly with the fixed text. A second window left by the earlier WSL pass holds identical content, so the capture alone does not identify which window is this run's; the journal does, because it records this run opening its own window and typing into it. After stopping only the assigned pid and restarting the same state, OpenAI stayed connected and default, the run row still served `200`, and the credential record's protected DACL was byte-identical before and after |
| OS-Q | WSL2 release and installed cua with Windows UI reachability; fresh state; OpenAI API key; Windows Notepad is available | Inspect WSL and Windows desktop session. Open Windows Notepad through the Windows UI, enter the fixed scratch text in an unsaved document and inspect it through the Notepad UI. Do not open or save a WSL path. Restart Vadgr and confirm provider persistence | Health says WSL; real usage and installed cua calls complete; Windows editor UI read-back agrees; provider persists with `0700`/`0600` controls | Formal run ids, journals/frames, Notepad UI read-back, provider and credential matrix | Close only the test unsaved document without saving; stop only the isolated daemon | pass on `ed99bdb`: `run-67087e98a8964990a511da089a58c4f0` completed in 1 m 10 s over 19 model responses, under the 20 ceiling, using 173,143 input and 725 output tokens on `gpt-5.6-sol`. Health reported `platform: wsl` with `computer_use: true`. The journal records the real cross-OS sequence through the installed cua: `get_platform_info`, screenshot, `win`, screenshot, `type_text Notepad`, screenshot, `enter`, a 2 s wait, screenshot, `type_text` of the two fixed lines, a full screenshot, then `screenshot_region` over the Notepad text area, which is the UI read-back oracle. No filesystem or application-open tool was called at all, so nothing was opened, created or saved and no WSL path was touched. Independent oracle: a separate capture of the Windows desktop shows Notepad holding exactly `Vadgr dogfood` and `Verified through editor UI`, with an unsaved marker on its tab and its own status bar reading `Ln 2, Col 27` and `40 characters`. After stopping only the assigned pid and restarting the same state, the provider persisted: OpenAI stayed connected and default on the identical reference `cred_v1_f72e8f0c...`, the directory stayed `0700` and the record stayed `0600`, and the run row still served 200. |

## Part C: full product path and engine behavior

Every row here names the run id, commit or released artifact it was observed on,
and that attribution is the row's provenance. An earlier version of this
paragraph said only rows citing `9761f6a` were E2E results, which stopped being
true as cells were re-run at later commits: `C02` was observed at `21f6078`,
`C14`, `C15` and `C17` were re-run against a deterministic provider fixture with
their run ids recorded, and `C22` was re-run against released cua `0.7.1`. Read
each row's own attribution rather than a single commit named here.

**The same matrix on native Linux: 21 pass and 4 partial.** Every row below
names the run it was observed on, all at `14b995b` with installed cua `0.7.2`,
and the observations come from this pass's own journals rather than from a
platform that already ran them.

`C01` and `C02`: the three re-run credential paths each drove a fresh run
through the installed cua from a connected default provider,
`run-6f9db82c` with 3 calls, `run-42b7d9e2` with 4 and `run-bdb45fc3` with 4,
and in every completed run each `in_flight` carries exactly one terminal.
`C03` to `C06`: `control__todo_write` opens the multi-step goals in
`run-10ef6e9a`, `run-b0d11c4d` and `run-9d0af770`; `control__todo_update`
follows on an existing list 3, 3 and 5 times; `control__report_progress`
records intermediate milestones 3 and 5 times; and `control__get_run_status`
reads the run's own state back inside `run-b0d11c4d` and `run-9d0af770`.
`C10` is that same progress record, which reaches the owner without asking for
an answer. `C11`: the text-returning tools are exercised as `fs`, `shell`,
`env`, `get_platform_info` and `ui_tree` across those runs. `C12`: `run-10ef6e9a`
called `screenshot` in `png` at sequence 9 against a real visible desktop and
the next provider turn continued with `ui_tree`, so the image result reached
the following turn rather than ending the run. `C13`: in `run-b0d11c4d` one cua
call errored and the loop corrected itself and carried on rather than failing
the run. `C18`: all four completed runs end with no dangling record. `C19`: the
failed run `run-992e7b0f` kept its row with a named error, and its provider
connection and 51 model catalog both survived. `C20`: `run-b0d11c4d` and
`run-9d0af770` were each killed with a cua call open and continued in the same
journal file after the restart.

`C14`, `C15` and `C17` ran against a deterministic provider fixture on this
host, and each failed by its own name rather than a shared one: `end_turn`
before any completed tool gave `NO_ACTION_TAKEN`, `max_tokens` without a tool
gave `provider response was truncated at max_tokens`, and a fixture that emits
a valid nonterminal turn for ever gave `agent did not finish in 100 iterations`
after the fixture had counted exactly 100 run turns, so the provider request
count and the iteration limit reconcile. `C16` pointed the completion endpoint
at a closed port: the run was accepted and then failed with
`provider request failed` naming the exact URL. `C22`: a `sleep 300` cua call
was recorded `in_flight`, the terminal cancel returned exit `0`, no journal
`done` appeared for it, and the owned child was gone within three seconds.
`C23` to `C25`: with the runtime present and enabled every live run above
proves the normal path; disabling computer use left `available: false`, spawned
no cua child and failed a cua-requiring run with `NO_ACTION_TAKEN`; and pointing
the daemon at an absent runtime left `available: false` with health reporting
`computer_use: false`, so it fails closed rather than pretending.

`C21` is `partial` and `F34` is why. Cancelling a run while its provider
request was open moved the row to `cancelled` and left both sockets silent. The
supervisor never broadcast a terminal on the cancelled path at all, which is
now repaired: the raw socket carries `agent_cancelled` and `run_cancelled`. The
cell still reads `partial` because its oracle asks for both sockets, and the
phone stream's frame vocabulary is frozen with no member that means cancelled.

The carried matrix is 25 explicit cells: two live boundaries, all eight control
tools, both content shapes, one tool error, four terminal outcomes, three
journal/recovery states, two cancellation timings and three cua states.

| id | precondition and setup | goal or trigger | expected observable and oracle | evidence boundary | cleanup | status |
|---|---|---|---|---|---|---|
| C01 | Connected default provider; installed cua; fresh run | Complete a goal-level machine inspection | At least one real model response has nonzero usage and the run reaches a valid terminal state | Run row, response usage, journal, CLI | None | pass on `9761f6a`: OpenAI, Gemini and Anthropic corrected runs completed with nonzero usage |
| C02 | C01 setup | Complete a reversible machine action selected by the model | Installed cua advertises and executes the call; every `in_flight` has one terminal; independent read-back matches | MCP readiness, journal, effect read-back | Remove effect | pass on `21f6078`: installed `vadgr` used OpenAI API-key `gpt-5.6-luna`; cua wrote then read the exact reversible marker in three responses. |
| C03 | Fresh run with multi-step goal | Let the model plan its work | `control__todo_write` is selected, journaled and returned; streamed todo ids match the canonical result | Journal records, raw todo frame, run status | None | pass in formal A and hard-kill rerun |
| C04 | Existing todo list from C03 | Let the model advance at least two items | `control__todo_update` changes only named ids; later status and restart preserve them | Journal, raw todo frames, status before/after | None | pass in dogfood and hard-kill rerun |
| C05 | Fresh run with observable intermediate milestones | Give a multi-stage goal long enough to report progress naturally | `control__report_progress` is selected; raw stream carries the exact progress while the run remains active | Journal and raw/mobile stream at call boundary | None | pass on `21f6078`: the installed CLI run emitted one `control__report_progress` call and completed; retained raw and mobile replays reached terminal frames. |
| C06 | Active run with todos and prior usage | Ask the model to inspect its own progress as part of recovery | `control__get_run_status` returns the same run, usage and complete todo list | Journal result, API row, DB row | None | pass in hard-kill rerun |
| C07 | Goal contains one reversible gated shell action; approval channel attached | Let the model request approval; approve once | Durable `await_user`/approval state precedes the action; one approval resolves one call; action happens once | Journal before/after answer, channel record, effect read-back | Remove effect | partial on `21f6078`: public run parked durably on `request_approval`; the answer-and-continue action is re-owned by `0.6.0`, whose conversation route is the first reply surface. |
| C08 | Goal requires owner choice between two safe outcomes; answer channel attached | Let the model ask, then answer one option | `control__ask_user` parks durably; answer is returned once and determines the next action | Journal, channel record, resulting action read-back | Undo reversible choice | partial on `21f6078`: public run parked durably on `ask_user`; there is no shipped answer route in `0.4.7`. The continuation assertion belongs to `0.6.0`. |
| C09 | Goal asks for a plan before any machine mutation; answer channel attached | Let the model propose a plan, then accept or reject | `control__propose_plan` parks; no external action precedes acceptance; decision returns once | Journal, channel record, zero pre-approval effects | Remove any post-acceptance effect | partial on `21f6078`: public run parked durably on `propose_plan` with zero machine actions; acceptance/rejection continuation belongs to `0.6.0`. |
| C10 | Goal includes an observable owner notification without requiring an answer | Let the model notify while continuing | `control__notify_user` emits once on the active channel and journal closes the tool call | Journal plus channel/stream notification | None | pass on `21f6078`: one journaled notification and one progress call completed, with raw/mobile terminal replays. |
| C11 | Installed cua text-returning tool available | Let model inspect platform, environment or file text | Text result is returned to the next model turn without shape loss and supports final read-back | Journal response before/after tool and independent text read | None | pass on `9761f6a`: all three corrected provider runs matched independent text read-back |
| C12 | Installed cua screenshot tool and visible desktop | Let model inspect a screen only when needed | Image block reaches the next provider turn with valid media type; evidence copy redacts sensitive pixels without altering runtime journal | Journal metadata/hash, provider follow-up usage, redaction record | Close test window | pass in A/B/C |
| C13 | Reversible goal where one deliberately malformed cua call can be corrected | Let model receive one tool error and recover | Journal records `error`; model sees it, issues a corrected call and completes; no false terminal failure | Error and corrected call records, final read-back | Remove effect | pass in formal B |
| C14 | Provider fixture returns `end_turn` before any completed tool | Start through API and CLI | Run fails `NO_ACTION_TAKEN`; zero effects; raw/mobile terminal failure agrees with DB/journal | Fixture identity, run row, journal, both sockets, CLI exit | Remove fixture state | pass: `run-f06c44c6fe30448080f42a0107871984` failed `NO_ACTION_TAKEN` in 1 s with zero effects. The CLI line, the run row and `outputs.error` agree. |
| C15 | Provider fixture returns `max_tokens` without a tool | Start through API and CLI | Run fails as truncated, never completes, and performs zero effects | Run row/error, response/journal, sockets, CLI | Remove fixture state | pass: `run-fa4f1bd00d1442b38deb52b4f0d33171` failed with `provider response was truncated at max_tokens`, never completed, and performed zero effects. |
| C16 | Accepted run whose selected provider fails before or during model completion | Start and observe failure; manually resume only after row is failed | Named provider failure reaches DB, CLI and sockets; no fabricated usage/effect; old credentials remain | HTTP/CLI, run row, sockets, journal, provider rows | Restore provider reachability | pass in surface sweep |
| C17 | Deterministic provider fixture emits valid nonterminal turns until limit | Start through API and CLI | Exactly the configured iteration limit is attempted, then named terminal failure with no extra provider call | Provider request count, journal iterations, DB/sockets/CLI | Remove fixture state | pass: `run-a4790ce3fbd74c8ba6a7d41c38ad2319` failed with `agent did not finish in 100 iterations`, and the fixture recorded **exactly 100** provider requests for the run, with no extra call after the terminal failure. |
| C18 | Completed normal run with no dangling record | Restart daemon against the same DB/journal | Terminal row is not resumed; journal is unchanged; provider/default remain available | Checksums and rows before/after restart, daemon recovery log | Stop daemon | pass on `21f6078`: public restart left the completed journal byte-identical and the same run terminal. |
| C19 | Failed run with valid journal and restored provider | Call `POST .../resume` and `vadgr runs resume` once | Same run id becomes active; sequence and prior usage continue; no new row is invented | HTTP/CLI, DB row, journal prefix/suffix, sockets | Stop run if still active | pass on `21f6078`: a disabled-CUA `NO_ACTION_TAKEN` run resumed through terminal `vadgr` after CUA returned, kept its id and completed. |
| C20 | Active run killed during an open cua call | Restart same binary with same DB/state/runs | Boot resumes same id, inspects live state before retry, restores todos and completes without duplicate effect | D1-D7 bundle, journal/sockets/API/DB/read-back | Remove marker | pass on `5558cf6` |
| C21 | Model request active and no cua call yet open | Cancel through API/CLI | Provider wait is cancelled; row and both sockets say cancelled; no retry or later completion overwrites it | Timing marker, HTTP/CLI, DB, sockets, journal | None | partial on `14b995b` on native Linux, and the earlier `pass in surface sweep` is withdrawn on every platform that carried it. That row recorded an exit code and a database status and never captured the sockets its own oracle asks for, and `F34` shows they could not have answered: the supervisor emitted no terminal at all on the cancelled path, so a client watching either socket saw `run_started`, `agent_started` and then silence. Driven here with both sockets attached before the cancel and held for 90 seconds after it, against a provider endpoint that accepts the connection and never replies: the row reached `cancelled` and no retry or later completion overwrote it, and neither socket carried a terminal. After the repair the raw socket carries `agent_cancelled` and `run_cancelled`; the phone stream stays silent because its frame vocabulary is frozen with no member meaning cancelled, which is the owner decision recorded in `F34`. The cell is `partial` rather than `pass` because its oracle names both sockets |
| C22 | Long cua call recorded `in_flight` and cancellable | Cancel through API/CLI while the child call is open | Call and run cancel promptly; no terminal `done` appears after cancellation; child cleanup is bounded | Timing marker, process tree, journal, DB, sockets | Remove reversible effect; stop child if owned | pass on `14b995b` on native Linux with installed cua `0.7.2`: a `sleep 300` call was recorded `in_flight`, the terminal `vadgr runs cancel` exited `0`, the row reached `cancelled`, no journal `done` appeared for the open call, and the owned child was gone within three seconds. **The WSL result below is owed again**: `F34` changed which frames a cancel puts on the raw socket, and this cell's evidence boundary names the sockets, so its earlier evidence describes a build that no longer exists. Previously, pass on WSL with installed CUA `0.7.1`: terminal `vadgr runs cancel` made `run-c6774f9e832c4479b13021f2591c7b96` cancelled with no journal `done` and no owned `sleep 30` process after five seconds. Native-OS reruns remain open. |
| C23 | Computer use enabled and installed cua executable present | Probe status, then run a cua-requiring goal | Status is available and run dispatches through installed cua | Settings/status, process argv, journal and read-back | Stop owned child | pass on `9761f6a`: public status and installed-cua journal calls agree |
| C24 | Computer use disabled before run | Probe status and start a goal that would require cua | Status is disabled; cua is not spawned; run receives the named unavailable path rather than silently acting | Settings/status, process snapshot, run/journal/sockets | Restore enabled setting | pass on `21f6078`: public status was unavailable; a CUA-requesting run failed `NO_ACTION_TAKEN` after the model received the unavailable surface, and no CUA process started. |
| C25 | Computer use enabled but configured runtime absent | Probe status and start a cua-requiring goal | Status is unavailable with named reason; no child starts; run fails or reacts through the published error path | Status body, process snapshot, run/journal/sockets | Restore runtime path | pass on `21f6078`: an absent configured executable produced unavailable status, no child process and the named no-action failure path. |

**Part C on native Windows: 25 of 25.** Each cell ran on its own state, port and
daemon. The control-tool cells are driven by scripting the provider's calls,
which is the only way to make one specific control tool the subject of a cell.

| cell | Windows observation |
|---|---|
| C03 | `control__todo_write` selected and journaled; the canonical list came back with both ids |
| C04 | `control__todo_update` advanced exactly the two named ids |
| C06 | `control__get_run_status` returned the same run id, its iteration, its todos and its token counts |
| C07 | parked durably at `awaiting_approval` with one `await_user` entry |
| C08 | parked durably on `control__ask_user` |
| C09 | parked durably on `control__propose_plan` with zero machine actions first |
| C10 | one journaled `control__notify_user`, and the run continued to completion |
| C13 | a malformed cua call returned an error, the model issued a corrected call, and the effect read back exactly |
| C16 | the provider stopped answering after its connection was committed: the run failed with `the provider is unavailable`, produced **zero** responses and **zero** tool calls, so no usage or effect was fabricated, and the credential record and connection were untouched |
| C20 | pass on `13074d3`: killed during an open cua call with todos outstanding. Boot resumed the same run id at `resumed=1`, the completed effect kept its inode, modification time and `sha256`, exactly one `fs` write to it appears in the whole run, the todos were restored and took four further updates after the kill sequence, and the run completed. The mobile socket carried five `todos` frames. |
| C22 | cancelled while a 90 second cua call was open: the CLI exited `0`, the row reached `cancelled`, **no terminal `done` arrived for the open call afterwards**, and the late effect the child would have written never appeared |

`C05` and the eight closed against a deterministic provider follow below.

| cell | Windows observation |
|---|---|
| C14 | `NO_ACTION_TAKEN`, one response, zero tool calls, zero effects |
| C15 | failed with `provider response was truncated at max_tokens`, never completed |
| C17 | failed with `agent did not finish in 100 iterations`, and the fixture recorded **exactly 100** provider requests for that run |
| C18 | restart left the completed run terminal and its journal byte-identical |
| C19 | `vadgr runs resume` exited `0`, the same run id became active and completed |
| C21 | cancel during an open provider wait returned exit `0` and the row reached `cancelled` |
| C24 | computer use disabled: the run received the unavailable surface and failed by name, with no cua child |
| C25 | computer use enabled with an absent configured runtime: same named failure, no child started |

Five more are carried by the live Windows runs rather than by a fixture: `C01`
and `C02` by the three Part A runs, which each completed with nonzero usage and
an exact independent read-back of a reversible effect, `C11` by the same text
read-back, `C12` by the `OS-W` run whose journal carries five image results
feeding the next provider turn, and `C23` by `OS-W`, where the public status and
the installed-cua journal calls agree.

Two fixture faults were found and corrected while driving these rather than
being filed as product results. `control__request_approval` was called with
`summary` and `detail` when its schema requires `action`, `risk` and `preview`,
so it errored instead of parking. Corrected, it was then called with `risk: low`,
which the default policy auto-allows by design, so it approved instead of
parking. Only at `risk: high` does the request reach `NeedsHuman`, which is the
state `C07` is about. Both readings looked like a product failure to park.

**`E03` on native Windows passes, and it is the strongest result of this pass.**
`run-123c399e54a4404fb29ebdf5d258dc74` on `gpt-5.6-luna`, 21 responses. The kill
moment was observed rather than timed: the harness waited until the fixed text
had been typed at sequence 11 and a later cua call was durably `in_flight` at
sequence 12, then killed only the assigned pid. The journal kept before the kill
is a byte-identical prefix of the final journal. The run resumed and completed.

Two observables matter most. The fixed text appears **exactly once** across the
whole journal, so the editor work was not repeated. And the first three calls
after the restart are all `computer-use__screenshot`, which is an inspection of
the editor's live state before any retry, which is precisely what the cell asks
for. Independent oracle, captured outside vadgr and outside cua: the Notepad
window holds exactly the two fixed lines, unsaved, with its own status bar
reading `Ln 2, Col 27` and `40 characters`.

That also bears on F28. `D06` went undemonstrated because its fixture had
nothing left to do after recovery, not because the loop never inspects: given
remaining work, this run inspected first.

**Part E on native Windows: 5 of 5.** `E01` and `E02` are closed by the `OS-W`
run, whose journal holds 14 tool calls of which 13 are installed-cua calls and
one is a control call, so no operator mutation substitutes for cua, and the
exact fixed text was read back through the editor UI. `E04` reconciles exactly:
15 model calls, 126,926 input and 676 output tokens on `gpt-5.6-luna`, which at
the price this runbook checked on the execution date is **USD 0.0262**, and the
source is the published model page rather than a guess. `E05` reconciles to
**zero**: the journal records no `await_user` entry and no approval, question or
other human contact.

For every successful engine cell, raw and mobile streams are captured from
before run acceptance through the terminal frame and reconciled with the same
journal. The A/B/C formal passes each reached `run_completed` and `completed`.

## Part D: hard-kill restart continuation

This group was run under the corrected public method on `ed99bdb`. An earlier
version of this paragraph recorded the corrected result as `not run`, while the
per-OS matrix above claimed the group as a WSL pass; the matrix was the wrong
half, and the group was then run for real rather than argued about (F23).

The kill moment is observed, never timed: the harness waits until the completed
effect is readable and one cua call is durably `in_flight` with no matching
`done`, and only then sends `SIGKILL` to the single assigned pid. The uncertain
action is chosen to leave a real effect, because an action with no effect cannot
exercise D05 or D06 at all.

The group starts from one connected provider, installed cua, a fresh DB/state/
runs root, both sockets attached, a reversible marker absent, and the exact
assigned daemon PID recorded. It captures at the kill boundary and again at
terminal completion, then removes the marker and stops only its own daemon.

**The statuses in this table are the WSL execution.** The same seven cells were
later driven on native Windows, where three of them fail, and that result is
recorded immediately after the table rather than merged into these rows.

| id | trigger/action | expected observable and oracle | evidence boundary | status |
|---|---|---|---|---|
| D01 | Wait until the marker is readable and its creating cua call is durably `in_flight`, then send `SIGKILL` only to the assigned daemon PID | Process exits without graceful completion; DB remains running; both sockets close abnormally | PID, process/port snapshot, marker metadata, pre-kill journal and socket closes | pass on `13074d3`, re-run on WSL after the resume replay changed. The kill landed at an observed moment: the completed effect was readable and a `computer-use__shell` call was durably `in_flight` at sequence 3 with no matching `done`. The process exited without graceful completion, the port stopped serving, the database file remained, and both public sockets closed abnormally at 1006. The uncertain action's own effect was still absent, and its child did not survive the daemon. |
| D02 | Restart the same release with identical database, state and journal roots | Same run resumes automatically from the next journal sequence, with no owner resume request | Restart log, health, run id and first post-restart sequence | pass on `13074d3`: restarting the same release on identical roots resumed the same run by itself, logging `run recovery scan complete resumed=1 parked=0 failed=0`, with no owner resume request. |
| D03 | Compare journal prefix before kill with final journal | Prefix is byte-identical and sequence increases monotonically in the same file | Pre/final journal hashes and sequence report | pass on `13074d3`: the journal kept before the kill and the same prefix of the final journal share one `sha256` (`0e0c3e82`), so the prefix is byte-identical and the run continued in the same file. The sequences run 0 to 12 without ever going backwards across the kill. |
| D04 | Compare completed marker effect before and after recovery | Completed side effect is not repeated; inode, modification time, hash and content are unchanged | Marker metadata/read-back before and after | pass on `13074d3`: the completed side effect was not repeated. After recovery `marker-effect.txt` carries the same inode `11941`, the same modification time, the same size and the same `sha256` `ad85eb8b` recorded at the kill boundary. This is the assertion that failed on native Windows before the replay repair, so it is the one this re-run exists for. |
| D05 | Count the dangling shell action across final journal/process evidence | Boot does not blindly redispatch it; the shell effect appears once | Tool sequence/count and process record | pass on `13074d3`: exactly **one** `fs` write to the completed effect appears across the whole run, at sequence 1. Boot did not redispatch the dangling `computer-use__shell` at sequence 3; the loop chose its own next action instead. |
| D06 | Inspect the first post-restart external call | Live-state read occurs before any decision to retry the uncertain action | Ordered post-restart tool records | pass on `13074d3`, and more strongly than before the replay repair. After the restart the first two external calls were both live-state reads: `computer-use__fs` with `op: read` on the uncertain effect's path at sequence 4, which errored because the file was absent, then a `computer-use__shell` `ps` listing at sequence 5 to see whether the killed command was still running. Only at sequence 6 did the loop re-issue the command. The reads came before any decision to retry. |
| D07 | Let the resumed run terminate and reconcile every surface | Database, API, journal and both sockets agree on completed status and usage; restored todos accept later updates | Final API/DB rows, raw/mobile terminal frames, journal/usage and todo report | pass on `13074d3`: the resumed run terminated `completed` and every surface agrees. The database row, the public `GET /api/runs/<id>` and the journal all report `completed` with 92,060 input and 1,390 output tokens, and the public `vadgr runs list` shows the same run. Both sockets reach their terminal frame, and the mobile stream carries a `run_resumed` frame, so the resume is observed on the wire rather than inferred. |

**The same group on native Linux, and all seven cells pass there.** Run at
`14b995b` against installed cua `0.7.2`, `run-b0d11c4db4b84c21828253e883eb0016`
on `gpt-5.6-luna`, 11 responses for 113,125 input and 1,070 output tokens.

`D01`: the harness waited for the observed moment rather than a timer. The
completed effect was readable and a `computer-use__shell` call was durably
`in_flight` at sequence 6 with no matching terminal, and only then did the pass
send `SIGKILL` to the one assigned pid. The process exited, the database file
remained, the port stopped serving, both public sockets closed abnormally at
`1006`, the uncertain action's own effect was still absent, and the killed
daemon left no surviving child. `D02`: restarting the same release on identical
roots resumed the run by itself, logging
`run recovery scan complete resumed=1 parked=0 failed=0`, with no owner resume
request. `D03`: the journal kept before the kill is a byte-identical prefix of
the final journal, both `sha256 b015f296`, and the sequences run 0 to 16 without
ever going backwards across the kill. `D04`: the completed effect was not
repeated, carrying the same inode `19584`, the same modification time to the
nanosecond, the same size and the same `sha256` as at the kill boundary.
`D05`: exactly one `fs` write to that effect appears across the whole run, at
sequence 1, and boot did not redispatch the dangling sequence 6; the loop chose
its own next action. `D06`: after the restart the first calls were live-state
reads, an `fs read` of the completed effect and an `fs stat` of the uncertain
one, which errored because the file was genuinely absent, then a `shell` process
listing to see whether the killed command still ran. Only after those three did
the loop re-issue the command. `D07`: the resumed run terminated `completed` and
every surface agrees. The database row, `GET /api/runs/<id>`, the journal and
`vadgr runs list` all report `completed` with 113,125 input and 1,070 output
tokens, both sockets reach their terminal frame, and the raw socket carries a
`run_resumed` frame, so the resume is observed on the wire rather than inferred.

**The same group on native Windows, and three of its cells fail there.** Run at
`dfa80c8` with `gpt-5.6-luna`, `run-ae4ccad3802349e3b55b97637ac3d363`, 8
responses for 23,550 input and 503 output tokens.

`D01` passes: the harness waited until the marker was readable and one
`computer-use__shell` call was durably `in_flight` with no terminal, then killed
the one assigned pid. The process exited, the database survived, and the
uncertain action's own effect was still absent at the kill boundary. `D02`
passes: restarting the same release on identical roots logged `run recovery scan
complete resumed=1` with no owner resume request. `D03` passes: the pre-kill
journal is a byte-identical prefix of the final journal and the sequence numbers
never go backwards. `D07` passes: the database, the public API, the journal and
the CLI all agree the run completed.

`D04`, `D05` and `D06` failed on that run:

- `D04`: the completed side effect **was** repeated. The marker's `sha256`, size
  and contents were unchanged, but its modification time moved, which is the
  cell's own oracle for a rewrite.
- `D05`: the dangling shell action appeared **twice** in the final journal and
  its effect file existed, where the cell requires the effect to appear once.
- `D06`: the first external call after the restart was `computer-use__fs` with
  `op: write` of the marker, which is a retry.

This was not accepted on the first observation, because a deterministic fixture
can produce the same shape for its own reasons. It was reproduced with a real
model and a goal-level task, and the deterministic run on the same host supplied
the mechanism: the first provider request after the restart carried **zero**
`function_call` and `function_call_output` items, so nothing in the resumed
conversation told the model that the marker had already been written. Recorded
as F27 and repaired on this branch.

**After the repair, `D04` and `D05` pass on the rebuilt daemon `09cfc396`.** The
marker survives recovery with the same `sha256`, modification time, size and
contents, and the dangling `computer-use__shell` entry appears exactly once with
its effect appearing zero times. The run completed in 5 responses for 23,579
input and 627 output tokens, and every surface agrees.

**`D06` is still not demonstrated, and is not claimed as a pass.** The resumed
run made no external call at all: it read its replayed results, concluded no
further action was needed and finished. Nothing was repeated, which is what
`D04` and `D05` protect, but the cell's own observable, a live-state read before
any retry decision, never occurred. The loop asks for that inspection in prose,
and F27 is precisely the demonstration that a prose instruction is not a
guarantee. Recorded as F28.

The final rerun used source `5558cf6` and run
`run-6889e6bf31e44e309114f8c9ffe7078b`. It also proved that the reconstructed
todo list survived restart and accepted both subsequent updates.

## Part E: owner dogfood batch

The earlier file-based rows are superseded acceptance observations. The revised
E01 and E02 are currently `blocked`; E03-E05 are `not run`.

Each OS uses its native editor only: GNOME Text Editor on the Linux target,
TextEdit on macOS, and Notepad on native Windows and WSL. The agent creates an
unsaved scratch document, enters exactly the fixed two lines below, and reads
them through the editor UI. It must not open, create or save a project, WSL,
network or other filesystem path. The UI read-back in `trajectory.jsonl` is the
oracle, not the model's prose or a file read-back.

```text
Vadgr dogfood
Verified through editor UI
```

| id | precondition and setup | goal or trigger | expected observable and oracle | evidence boundary | cleanup | status |
|---|---|---|---|---|---|---|
| E01 | Installed release, OpenAI Platform API key, installed cua, isolated WSL state, Windows Notepad available | From the terminal, give the loop a goal to open Windows Notepad, enter the fixed two lines in a new unsaved document, inspect them through the UI and report them. Do not open or save a file. | One run reaches completed after real cross-OS UI work. Journaled editor action and UI read-back contain the exact two lines. | CLI, run row, journal with screenshot payload redacted, both sockets and editor UI action/read-back records | Close only the test unsaved document without saving. Leave unrelated Notepad processes untouched. | pass: `run-e9b91163b75b487dbf1db546a0a7d4e2` completed in 40 s and 11 model responses, under the corrected 20 ceiling. The journal records the real cross-OS sequence: screenshot, `win+r`, screenshot, `type_text notepad`, `enter`, wait, `ui_windows`, screenshot, `type_text` of the two fixed lines, screenshot. Independent oracle: a separate capture of the Windows desktop shows Notepad holding exactly `Vadgr dogfood` and `Verified through editor UI`, unsaved, with its own status bar reading `Ln 2, Col 27` and `40 characters`. No file was opened, created or saved. This is the same path that failed before the F20 repair. |
| E02 | E01 setup and an unsaved test document | Let the model choose cua as hands for every machine action | No direct operator mutation substitutes for cua. Every external action is countable and the exact editor text is independently read through the UI. | Journal tool sequence, boundary audit and exact editor UI read-back | Close only the test unsaved document without saving | pass with E01: every machine action in the journal is a CUA call. Ten external calls, no operator mutation, and the text reached the document only through `type_text`. The read-back is the run's own capture plus the independent desktop capture named in E01. |
| E03 | Owner approves assigned daemon PID; same unsaved editor task as E01; both sockets attached before start | After the fixed text is durably read through the editor UI, kill only the assigned daemon with `SIGKILL` while a later cua inspection call is durably `in_flight`. Restart the same state and let the batch finish. | The same run continues. Journal prefix and todos survive. The first action after restart inspects editor UI state before any retry. The original text appears once and exact final UI read-back matches. | PID/kill point, pre/post journal, DB/API, both sockets and final editor UI read-back | Close only the test unsaved document without saving. Stop only the assigned daemon. | pass: the owner assigned the isolated daemon on port 8471 with its own database, journal and state. `run-a7cec6706852472196df68b440945479` was killed with `SIGKILL` while `computer-use__click` was durably `in_flight` with no terminal, after the fixed text had been read through the editor. Restarting the same state logged `run recovery scan complete resumed=1`, and the run completed. The journal grew from 8 entries to 27 with the prefix intact, and the **first two actions after the restart were `control__get_run_status` and `control__report_progress` naming the previously captured state, before any retry**. The text appears once and the final read-back matches. Only the assigned PID was stopped. |
| E04 | Completed revised E01 or E03 run plus an authoritative provider response, billed-account usage record or owner-approved pricing rule | Reconcile run usage to elapsed time, model calls, input/output tokens and monetary amount | Record names source and currency and either an exact amount or an owner-approved `unavailable` disposition; no guessed subscription price | Run metrics, provider/account record with secrets removed, calculation and disposition | Remove any sensitive account capture after redacted facts are filed | pass: `run-e9b91163b75b487dbf1db546a0a7d4e2` reconciles exactly to 11 model calls, 93,352 input and 572 output tokens, and 39.97 s elapsed, all read from the journal and the run row. The owner directed that the amount come from the billed-account usage record, which is one of the three sources this cell names. Source: the provider's platform usage dashboard, read at `2026-08-17T00:47-05:00` and filtered to the single dedicated API key this product uses. Currency: USD. Billed record for that key on `2026-08-17`: **$0.38 total spend across 51 requests and 612,927 tokens**, whose largest line items are the run's model under cache-write, cached-input and output categories. **The per-run amount stays `unavailable`, now with the reason observed rather than assumed**: the dashboard's finest granularity is one day, its stored response log returns zero results so no per-call cost record exists, and its line-item cards carry a cost without a token count, so no exact per-category rate can be derived. The run is 11 of those 51 requests. No subscription price is guessed and no share is computed from a blended rate. |
| E05 | Revised E01 or E03 complete | Count every approval, question and other human intervention from channel records | Exact contact count and reasons reconcile with journal `await_user` records | Channel record, journal count and summary | None | pass: `run-e9b91163b75b487dbf1db546a0a7d4e2` records zero `await_user` entries and the channel shows no approval, question or other human contact. Exact contact count is 0, and it reconciles with the journal. |

**The same batch on native Linux, and all five cells pass.** The editor here is
GNOME Text Editor on a Wayland session, driven through the accessibility tier
rather than through pixels, which is the Linux shape of this group.

`E01`: `run-83de02e8c0f3431f89518ce0612de2b8` completed on `gpt-5.6-luna` in 8
model responses for 76,011 input and 573 output tokens, in 20 seconds. The
journal records `apps`, `app_open org.gnome.TextEditor.desktop`, `ui_tree`,
then `ui_act set_text` of exactly `Vadgr dogfood\nVerified through editor UI`,
then two `ui_tree` reads as the UI read-back. `E02`: every machine action in
that journal is a cua call, six of them, with no operator mutation and **no
filesystem tool call at all**, so the text reached the document only through
`set_text` and nothing was opened, created or saved. The read-back is the run's
own `ui_tree`, not a file read and not the model's prose. `E05`: the journal
holds zero `await_user` records and no approval, question or other human
contact, so the exact contact count is 0 and it reconciles with the journal.
`E04`: 76,011 input and 573 output tokens on `gpt-5.6-luna` at the official
published rate of USD 0.20 per MTok input and USD 1.20 per MTok output is USD
0.015890, calculated from the run's own recorded usage and the provider's
current price page rather than from a remembered figure.

`E03` is its own run, because the first attempt's kill landed after the run had
already finished and that attempt was kept as `E01` rather than reported as a
kill. `run-9d0af770d0ee4c01af690802c29f6853` was given the same editor task with
five spaced inspections. The harness waited until the fixed text was durably in
the journal and a later cua inspection call, `ui_tree` at sequence 9, was
`in_flight` with no terminal, then sent `SIGKILL` to the one owner-assigned pid.
Both sockets closed at `1006`, the editor window stayed open, and the restart
logged `resumed=1`. The journal kept before the kill is a byte-identical prefix
of the final one, both `sha256 8bb0ff87`, and the sequences run 0 to 26 without
going backwards. The first action after the restart is a live `ui_tree` read of
the editor, before any retry, and the todos were restored and accepted later
updates. **`set_text` appears exactly once across the whole run**, so the
original text was never re-typed. The final read-back at sequence 24 shows the
window titled `Vadgr dogfood Verified (Draft) - Text Editor` holding the two
lines, and the independent oracle taken outside both vadgr and cua, GNOME Text
Editor's own draft in its private state directory, is byte-for-byte the two
fixed lines plus the editor's trailing newline. The run finished `completed` in
18 responses for 352,164 input and 1,621 output tokens, USD 0.0724, inside the
40 iteration and USD 0.50 ceilings. At cleanup the test document was closed
without saving and the isolated draft removed; no user file was ever created.

## Repeatability - three independent acceptance passes

Three passes used separate ports, databases, state roots, run roots, daemons,
installed terminal commands and provider attempts, and all three ran at the same
time. All three pass.

The earlier attempt recorded R01 as a fail, because a monitor cancelled it at a
six-response ceiling before it read the marker. The ceiling was the harness's,
not the product's, so that result measured the harness. The group was re-run
whole rather than R01 alone, because three passes are only independent
observations when they run concurrently, and re-running one against two older
results would prove nothing about ordering or interference.

**Each pass now carries its own marker value** rather than the single shared
string the first attempt used. A shared marker cannot tell an isolated read from
a pass that reached another pass's file; three different markers, each returned
by its own pass, make the isolation an observation. The fixture is still
identical, which the token counts confirm: turn-0 input is exactly 5,488 on all
three, so the three prompts matched. R02's turn-0 output ran 11 tokens longer
than the other two and its turn-1 input is 11 tokens larger, which is the same
11 tokens fed back, so the difference reconciles rather than drifting.

| id | corrected pass requirement | result |
|---|---|---|
| R01 | Pass A uses its own port, database, state, runs, daemon and terminal `vadgr`; reconcile HTTP, CLI, raw socket, mobile socket, journal and usage | pass on `ed99bdb`: `run-b01063703ce74a17adf84ef863d5ac15` on port 9491 completed in 7 s over 2 responses, returning its own marker `vadgr-repeatability-R01-20260817` exactly. All six observables agree: HTTP reports `completed` on `gpt-5.6-sol`, the CLI lists the same run, the journal holds 2 responses with a single `computer-use__fs` call, journal usage equals HTTP usage at 11,037 input and 51 output, and both sockets replay 5 frames each to their completed terminal frame. |
| R02 | Pass B runs the identical fixture concurrently with R01 and R03 under its own isolated resources | pass on `ed99bdb`: `run-0f454fec81c44261aa119c2d632f9283` on port 9492 completed in 7 s over 2 responses, returning its own marker `vadgr-repeatability-R02-20260817` exactly, with 11,048 input and 62 output. Same structure and the same 5 frames on each socket. |
| R03 | Pass C runs the identical fixture concurrently with R01 and R02 under its own isolated resources | pass on `ed99bdb`: `run-382c160a2f894dc1982b22c2e6f17210` on port 9493 completed in 7 s over 2 responses, returning its own marker `vadgr-repeatability-R03-20260817` exactly, with 11,037 input and 51 output. Same structure and the same 5 frames on each socket. |

The following table records the superseded acceptance observations only.

| | pass A | pass B | pass C |
|---|---|---|---|
| run | `run-1ce4abf3fa184847928dac457f685842` | `run-21f9bcb4e5e44609ae460581d0df6b43` | `run-db0e530b08d34ce08f26df69e505756b` |
| HTTP entries | accepted and completed | accepted and completed | accepted and completed |
| CLI entries | login/readiness and persisted state captured | login/readiness and persisted state captured | login/readiness and persisted state captured |
| raw / mobile frames | `8 / 5`, terminal | `5 / 5`, terminal | `5 / 5`, terminal |
| journal phases | `19 / 19`, no error | `16 / 16`, 2 handled errors | `11 / 11`, no error |
| tokens in / out | `1,077,574 / 1,286` | `913,612 / 2,030` | `317,047 / 796` |

The three runs began with the same 5,458-token input fixture. Their first output
counts and later trajectories differ, proving independent model calls. The
comparison normalizes only run id, timestamp, port, and provider request id.

## Evidence

The final private evidence lives under `e2e_evidence/vadgr-0.4.7/`. It
contains the source commit and binary checksum, generated surface sweep and
tables, CLI transcripts, provider rows, redacted credential metadata and
effective-control checks, databases, journals, socket frames, daemon logs,
comparison output, and a checksum manifest. Secrets and authorization headers
must not be present.

## Findings

| id | finding | root cause | repair and regression | rerun |
|---|---|---|---|---|
| F1 | The first `scratch` start exited before readiness with `provider request failed: builder error`. | Reqwest selected the platform certificate verifier. A `scratch` image has no system certificate store. | The provider client now supplies a Rustls configuration with embedded Web PKI roots. The clean-install test remains the regression because it starts with no host files or libraries. | pass: the exact static artifact served health and providers from `scratch` |
| F2 | Docker Desktop first returned health with `platform: wsl` from the Linux container. | The container shares a Microsoft WSL kernel, and host detection treated that kernel marker as direct WSL. | Linux container markers now take precedence over WSL markers. A unit test keeps direct WSL as `wsl` and a container as Linux. | pass: health returned `platform: linux` from `scratch` |
| F3 | The first direct ChatGPT connection returned no usable models, then readiness returned HTTP 400 after catalog discovery was repaired. | The catalog used Vadgr `0.4.7` as a ChatGPT protocol capability version, and the Responses body sent `max_output_tokens`, which the native ChatGPT route does not support. | The catalog has an explicit protocol version independent of the product version. The ChatGPT request omits the unsupported field while the API-key request retains it. Both boundaries have regression tests. | pass: browser OAuth, catalog discovery, bounded readiness, credential commit, and default selection completed |
| F4 | The first real OpenAI run consumed tokens but failed with `NO_ACTION_TAKEN`; its journal contained no tool call. | ChatGPT delivered the completed item in `response.output_item.done` while `response.completed` carried usage and an empty output array. The decoder read only the terminal frame and discarded the streamed item. | The SSE decoder accumulates completed output items and uses them when terminal output is empty. A regression test reproduces the live event sequence. | pass: the rerun completed in 12 iterations with installed cua calls, nonzero usage, matched journal phases, one handled tool error, and a final verified report |
| F5 | The CLI printed the fallback authorization URL after a successful browser launch and hid it after a failed launch. | Click returns process-style status `0` for a successful launch, but the branch treated that value as false. | The branch now compares the launch status to zero explicitly. A regression test forces a nonzero result and requires the URL in output. | pass: focused provider CLI suite, 9 tests |
| F6 | WSL did not open the Windows browser, and an E2E-only `cmd.exe start` workaround delivered a malformed OAuth request with missing parameters. | Click's Linux launcher could not cross the WSL desktop boundary. The command-shell workaround also gave `cmd.exe` an OAuth URL whose query delimiters are shell syntax. | WSL now invokes a fixed Windows PowerShell script without a shell-built URL and sends the complete authorization URL over stdin. Tests require that the URL is absent from argv and preserved exactly as input. Other platforms retain Click's native launcher. | pass: focused provider CLI suite and three live browser launches from WSL |
| F7 | The formal work-run screenshots captured the spent OAuth callback query from Chrome's address bar. A denied callback also rendered the connected page. | The callback returned its final HTML directly on the URL that carried `code` and `state`, and the route treated a cleanly recorded cancellation as a successful connection. | Every callback now redirects to a parameter-free completion or failure route. A route-level regression requires `303`, a query-free `Location`, a generic final page, and failure status for cancellation. Evidence copies replace affected screenshot payloads with explicit redaction records while preserving hashes and sizes. | pass at affected boundaries: focused route regression, live reauthentication, readiness and commit; visual address-bar read-back unavailable because the owner closed the completion tab |
| F8 | The hard-kill run resumed safely but its next `control__todo_update` returned `unknown todo id`. | The journal recovered model usage, recent results and external-call state, while `RunContext` recreated its control todo list as empty. | Recovery now reconstructs the canonical list from successful journaled `todo_write` and `todo_update` results before the MCP host starts. Tests cover both reconstruction and a successful update through a restored control server. | pass: final hard-kill rerun restored all todos and completed both later updates |
| F9 | Gemini rejected the first full tool-bearing request although catalog discovery and readiness passed. | Gemini's schema dialect rejects `additionalProperties` and requires `items` on every array, while the neutral CUA and control schemas included both unsupported and incomplete shapes. | The Gemini adapter recursively removes `additionalProperties` and supplies an empty schema for arrays without `items`. Regression tests cover nested objects and arrays. | pass: the live request reached installed CUA |
| F10 | Gemini completed its first tool turn, then rejected the follow-up request with HTTP 400. | Gemini requires its `thoughtSignature` to be replayed with the matching model function call, but the neutral tool-use block discarded provider metadata. | Neutral tool-use content now carries an optional provider signature. Gemini records and replays it; OpenAI and Anthropic leave it absent. Round-trip and adapter tests cover the field. | pass: `run-06d3f88bf81b4441acd0d6f34df02b89` completed three model iterations and the exact effect read-back |
| F11 | Anthropic's insufficient-credit response surfaced as a generic unavailable provider. | The adapter classified every non-success Messages response by status alone and did not inspect Anthropic's bounded error envelope. | The adapter parses the safe JSON error category and maps the low-credit 400 response to the existing quota-exhausted result without retaining provider prose or credentials. | pass at the affected boundary: the CLI now reports quota exhausted; live completion remains blocked until API credits are available |
| F12 | A fresh Gemini database produced `NO_ACTION_TAKEN` because installed CUA appeared disabled. | The harness isolated state, database and runs but inherited the owner's normal config directory, where computer use was disabled. | Every example and the executable harness now isolate `VADGR_CONFIG_HOME`, set the feature only in that isolated environment, and require the product status endpoint to report CUA available before submission. | pass: both later Gemini runs used installed CUA and completed with independent read-back |
| F13 | The additive preflight tried OpenAI Platform API-key authentication although A25 specifies ChatGPT OAuth plus Gemini API key. | The executable harness encoded a provider combination that differed from the approved cell even though both used the OpenAI provider id. | The harness now invokes the ChatGPT OAuth method and pins the proven general Gemini model from the authenticated catalog. | pass on `ed99bdb`: the owner approved the browser consent, and the corrected flow connected OpenAI by ChatGPT OAuth and Gemini by API key into one isolated state. The public `vadgr provider status` then reported OpenAI connected and default with a seven model catalog, Google Gemini connected with a twenty eight model catalog that contains the pinned `gemini-3.5-flash-lite`, and Anthropic not connected. The CLI printed `Default remains: OpenAI / gpt-5.6-sol` on the Gemini connect, so the coexistence rule in A25 and the default rule in A26 both hold on the current head. The Gemini key entered the process only through the environment variable the CLI detects, so no value reached a command argument. |
| F14 | Provider-neutral E2E work used expensive product starters without a dated model comparison or hard spend ceiling. | The runbook declared that credentials were billed but did not require capability/price research, an explicit cost-effective engine model, or cancellation thresholds; the harness inherited the provider default. | Shared engineering, both machine-side entry points and both E2E templates now require current official research, authenticated-catalog validation, explicit cheapest-capable models, bounded iteration/token/money ceilings and evidence-based escalation. This runbook selects Luna, Flash-Lite and Haiku for future generic engine work. | not rerun: the next authorized billed group must prove its driver cancels at the written ceiling |
| F15 | The WSL evidence called `python -m cli` from Python drivers while the runbook claimed the shipped terminal CLI. | The capture scripts replaced the public `vadgr` entry point. The review treated real daemon and wire activity as sufficient although the on-box user surface was bypassed. | Shared engineering, both machine-side entry points and both E2E templates now require the public command. This runbook reclassifies every affected live result as an acceptance diagnostic. | partial pass: API-key onboarding, three provider runs, 47 shipped HTTP rows, 30 absence probes, 25 CLI rows and six callback rows now use the corrected public boundary; remaining cells stay open |
| F16 | The corrected Gemini Flash-Lite run completed and matched its read-back, but used seven model iterations against the written six-iteration ceiling. | Foreground `vadgr run` watched the product outcome but no independent guard cancelled the run at the cost boundary. | Keep the six-iteration ceiling. The corrected rerun starts through terminal `vadgr`; a capture-only monitor invokes public `vadgr runs cancel` when the sixth response is durable. | pass: bounded `run-19fa499edbf94542b5d7b4321447d597` completed in two turns before cancellation, with 15,499 input, 106 output and exact read-back |
| F17 | The WSL/Windows dogfood attempt reached 27 responses although its monitor reported zero. | The monitor matched a spaced JSON form while the live JSONL used compact `"phase":"response"`; a second ad-hoc monitor was also not a valid pre-acceptance guard. The file-based goal also crossed the WSL filesystem boundary, which is not the owner task. | The 27-response attempt is invalid evidence. The revised editor-only E01 starts a pre-armed JSON-aware monitor before acceptance, checks its count against the journal, and never opens or saves a file. | the monitor is now proven and the ceiling was wrong. A JSON-aware monitor armed before acceptance counted the compact form correctly and cancelled `run-414cac0ed9774da7af1751f7b2b8422f` at its sixth response, through the public CLI. It cancelled one keystroke after `key_press win+r`, before Notepad could open. **Six responses is F16's ceiling for a one-step task and does not fit this cell**: E01 must plan, orient, capture, open an application, type two lines and read them back. The ceiling for E01 is 20 responses, recorded here rather than removed, because the guard worked and only its number was wrong. |
| F20 | E01 failed with `the provider quota is exhausted` after three read-only CUA calls. The account was not exhausted, and the message was wrong. | **The OpenAI adapter sends a screenshot to the model as base64 text.** A CUA image result carries `content:[{type:image, source:{data,media_type}}]` and no `text` field, so `tool_result_text` (`rust/src/engine/provider/openai.rs`) finds nothing to join and falls back to stringifying the whole content array into `function_call_output.output`. The failing run's own journal holds 739,560 characters of base64, about 185,000 tokens, against three prior calls of 5,497, 5,604 and 5,693 tokens and an organization ceiling of 200,000 tokens per minute. Three further defects hid the cause: `classify_status` maps every HTTP 429 to `QuotaExhausted`, so a rate condition is reported as an empty wallet; the failure body is never read, because the response is only decoded on success, which destroyed the upstream `code`; and the retry waits 500 ms then 1,000 ms and ignores `retry-after`, which cannot clear a per-minute window. | Repaired in the OpenAI adapter. A tool result carrying an image now rides as typed `input_image` parts instead of being stringified, which is the shape the service accepts and the model reads. `classify_failure` reads the upstream body and separates `insufficient_quota` from a pace condition, which is a new `RateLimited` error and a `rate_limited` category. The failure body is read on every path, including both catalog probes, so the upstream code survives into the message. Retries key off the classified error, honour `retry-after` capped at 60 s, and otherwise wait 5 s then 20 s. Each fix has a test that was seen red against the reverted logic. | pass: the same path now completes. A screenshot of 156,977 characters cost **1,447 input tokens** as a typed image, where the same payload as text would have been about 39,000. E01 then completed with four screenshots across 11 model calls for 93,352 input tokens in total. The earlier failing request carried 739,560 characters, roughly 185,000 tokens, against a 200,000 per minute ceiling. |
| F23 | The per-OS matrix claimed two parts as WSL passes that the section preambles below it called `not run`. | Part C's row read `24 of 28` and Part D's read `7 of 7`, while Part C's own preamble said only rows citing one commit were E2E results and Part D's preamble said the corrected result for `D01` to `D07` was `not run`. The corrected evidence boundary's summary lists provider onboarding, the surface sweep and repeatability, and never mentions a hard-kill sequence, so Part D had genuinely not been re-run. The matrix and the preambles were edited at different times and nobody compared them, which is the same drift the matrix rows were added to stop. | Part D was run for real under the corrected method rather than argued about, and its row now rests on that run. Part C's preamble was the stale half: several of its cells had been re-run at later commits with their run ids recorded, so the preamble now tells the reader to read each row's own attribution instead of naming one commit. Two checks were corrected as well, both being wrong in the same direction as the documents they guard. The runbook accounting had been counting an observation row as a run, which inflated its headline from 125 verdicts to 228; it now reports verdicts, owed and observations separately. The style check had been reading verbatim evidence captures as prose and failing on an em dash that a desktop application printed in its own window title, which is a check firing on correct work: its comment had always said captures were out of scope, and the code now does what the comment said. Both corrections were proved by planting the defect each claims to catch and watching it fire. | pass: the matrix, the preambles and the generated counts now agree. |
| F22 | The first attempt at the credential-storage group ran against a daemon binary that was not the commit under test. | The release binary on disk was built at 23:09, but `credentials.rs` changed at 23:49 and four later commits touched the credential store: naming the path when the owner check refuses, two platform repairs for macOS and admin Windows accounts, and closing the staged handle before publishing. Nothing in the harness compared the binary against the source, so every result would have been filed under a commit that did not produce it. | The mismatch was caught by an output that disagreed with the source: the wrong-owner refusal printed the old generic wording while the source had been changed to name the path and both uids. The binary was rebuilt and every cell in the group was re-run against it, which is when the detailed refusal appeared. The harness now records the daemon `sha256` in the evidence boundary, and a cell is filed against a commit only after the built binary is checked against that commit's source. | pass: the group was re-run end to end on the rebuilt binary and all of `BQ02` to `BQ08` hold. |
| F21 | The service lifecycle cell for the update preflight could not run, because the product has no preflight. | `vadgr update` runs `git pull --ff-only origin master` and then `pip install` directly. `vadgr update --help` offers no dry-run or check flag, so there is no way to ask what an update would do. The runbook's cell requires a check that reports the current and new version and the intended artifact without mutating the installation, and executing the only available path performs exactly the mutation the cell forbids. | Not repaired here. The command needs a check path that reports the current version, the new version and the artifact it would install, and changes nothing. Until then the cell cannot be executed as written by anyone, on any platform. | blocked: S12f. The other five service lifecycle cells pass. |
| F19 | Cancelling a live CUA shell call ended the Vadgr run but did not terminate the shell child. | Cancellation stopped the Rust dispatch future and later closed the CUA server, but the CUA child process was not cancellation-aware. | CUA `0.7.1` runs `shell.run` asynchronously, terminates its Unix process group or Windows process tree on cancellation, and has a focused regression. | pass on WSL against the released boundary. CUA `0.7.1` is merged and tagged; a wheel built from the tag (`sha256:d11240369ad3e326`) is installed **without editable mode in a fresh environment outside the checkout**, and `doctor` reports 33 tools. A public run opened `/bin/sh -c sleep 400` with its `sleep 400` child; public `vadgr runs cancel` ended the run and **both processes were gone five seconds later**. The earlier WSL result used an editable checkout install whose metadata still read `0.6.6` while running `0.7.x` code, so it could not support a `0.7.1` claim. Linux, macOS and Windows native reruns remain required. |

| F24 | The mandatory credential gate could not pass on native Windows, and had never run there at all. Preparing the Windows host was the first time anyone invoked it with `--env-file` on that platform. | `scripts/check_no_secrets.py` passed the target path as a trailing argument to `powershell.exe -Command`. PowerShell does not bind `$args` under `-Command`; it appends the remaining tokens to the command text instead. `$args[0]` was therefore always empty, `Get-Acl` received nothing, and the check failed closed on every file it was given. The gate reported `the local environment file must have an owner-only Windows DACL` whatever the real DACL was, so a correctly protected file and a world-readable one were indistinguishable. Two things hid it: CI runs the gate only on `ubuntu-latest` and never passes `--env-file`, so the Windows branch executed nowhere, and the gate had no test of its own on any platform. | The target now reaches PowerShell through an environment variable, which also keeps a path containing spaces or quotes out of the parser. Four tests cover it: the invocation contract, the script shape, a real accept and refuse round trip that grants a broad `S-1-5-11` entry through `icacls`, and a missing-target fail-closed. All four were seen red against the reverted script, and the gate itself was seen refusing the same correctly protected file. A new `gate-tests` job runs them on `ubuntu-latest` and `windows-latest`, because the defect survived precisely by having no test and one operating system. That new job then immediately earned itself by failing on a second cause the developer machine could not show: the check compared the file owner against the token user alone, but Windows makes the Administrators group the owner of anything an administrator creates, so the gate refused a correctly protected file on any admin account. The daemon's own credential store already accepts either the token user or the token default owner; the check now agrees with it, and the confidentiality guarantee is untouched because it rests on the broad SID list, which does not name Administrators. | pass: the gate returns `SECRET CHECK PASSED` against the owner-only workspace `.env` on native Windows 11, and the new job passes on both CI operating systems |

| F25 | `vadgr-cua doctor` cannot run on native Windows, which blocks the handoff step that requires recording it. | `computer_use/bridge/supervisor.py:22` imports `fcntl`, which is Unix only. The docstring on `_get_supervisor` at `computer_use/mcp_server.py:866` states the intent correctly: the supervisor must not load on native Windows, and only the daemon subcommands need it. `_cmd_doctor` at line 902 then calls `_get_supervisor().status()` unconditionally, so the code contradicts its own comment and the command dies before it can print anything. | Not repaired here, because the defect is in the computer-use repository rather than this one, and a patch there implies its own release. The verdict was probed rather than assumed: the installed `0.7.1` wheel was driven over its real stdio wire with an `initialize` and `tools/list` exchange, and it returned **33 tools** including the whole `ui_*` structured tier. So the hot path the daemon actually spawns is healthy and only the `doctor` subcommand is broken. The stdio probe is filed with the evidence and is the stronger oracle, because it exercises the wire a client uses rather than a status helper. | pass for the wire, blocked for `doctor`: the Windows cells that need the tool surface can proceed on the probe |

| F26 | On native Windows the structured tier answers a Windows caller with a Linux remedy. `computer-use__ui_windows` returns `at_spi_unavailable` with `No accessibility bus reachable. Enable it and install ...`, which names the Linux accessibility bus on a platform that does not have one. | The Windows structured tier is not built yet, which is correct for this cua minor and is scheduled work. The defect is the answer, not the absence. The tool is advertised in the 33 tool surface, so a model reasonably reaches for it first, and the reply sends it to enable a bus that cannot exist on Windows. The neighbouring `computer-use__apps` shows the honest shape on the same host: `apps_unsupported` with `No apps tier on Windows yet`. | Not repaired here, because it is in the computer-use repository. The remedy is to make the Windows arm report an unsupported tier the way `apps` already does, rather than a Linux enablement instruction. | observed in both completed Windows runs: it cost one wasted model turn each time, then the loop fell through to the pixel tier and completed, so it degrades rather than blocks |

| F27 | On native Windows a hard-kill resume repeated the completed side effect. `D04` and `D05` failed there while all seven passed on WSL. | `opening_messages` in `rust/src/engine/loop.rs` rebuilt a resumed run as prose: a count of completed steps, an instruction not to repeat them, and a summary of recent results. It never replayed the completed calls as the tool-use pairs they were, so the first provider request after a restart carried **no** `function_call` or `function_call_output` items. The deterministic run measured this directly: the pre-kill turns sent 1, 2 and 3 structured tool items and the first post-restart turn sent 0, while still carrying four role items and 29 KB of content. Not repeating a completed action therefore depended on the model obeying an instruction rather than on it reading a fact, and a live model did not obey it. | Repaired. Recovery now keeps each completed call beside its result (`RecoveredCall`) and replays them as real `tool_use` and `tool_result` messages, so a resumed conversation carries the same shape an uninterrupted one has. The prose keeps only what the replay cannot express: the step count and the dangling call's unknown outcome. A regression test asserts the assistant tool call and its matching result are present, and it was seen red against the reverted branch with `a resumed conversation must carry the assistant tool call`. | pass for `D04` and `D05` on the rebuilt daemon `09cfc396`: the marker's `sha256`, modification time, size and contents are all unchanged after recovery, the shell action appears exactly once, and its effect appears zero times. `D06` remains undemonstrated and is not claimed: see F28 |
| F28 | `D06` asks for a live-state read before any decision to retry, and nothing in the loop requires one. | After the F27 repair the resumed run made **no** external call at all. It read the replayed results, concluded no further action was needed, and completed. That satisfies `D04` and `D05`, because nothing was repeated, but it never demonstrates `D06`'s observable. The dangling-call text still asks the model to "inspect the live state first", and an instruction in prose is exactly the kind of guarantee F27 showed cannot be relied on. | Not repaired. Making `D06` an observable property rather than a request means the loop itself has to inspect the dangling call's state on resume and put that reading into the conversation, instead of asking the model to do it. That is a design change and it belongs to the owner. | `D06` not demonstrated on Windows, on `run-ae4ccad3802349e3b55b97637ac3d363`'s successor. It is not a repeat and not a failure of idempotency; it is an unproved assertion, and it is recorded rather than counted as a pass |

| F31 | The credential gate was repaired in one repo, and the same broken gate stayed in the other three. | `F24` fixed `scripts/check_no_secrets.py` in this repo, but the checker is meant to be identical in all four and the other three still passed the target as a trailing argument under `powershell.exe -Command`. Their gate therefore still refused every file on Windows, whatever the real DACL was. The cross-repository check reported six differences, three for the checker and three for its workflow, and nothing else would have caught it: each repo's own gate passes on Linux, so all four looked green. | The repaired checker, its new test and the workflow that runs the gate on three operating systems were propagated to the other three repositories. All four now run the same gate, all four pass on this host, and the gate's own test passes in each. | pass: the cross-repository check reports the four repositories consistent. |
| F30 | Two Rust source files gained a UTF-8 byte order mark, and every suite stayed green. | `rust/src/engine/journal.rs` and `rust/src/routes/providers.rs` begin with `EF BB BF` from commit `e324281`. Rust tolerates a leading BOM, so the compiler, `clippy`, `fmt` and all four suites passed, and the only visible trace was one line of diff noise on an unrelated `use` statement. No other file in the four repos carries one, and a BOM breaks concatenation, shebangs and tools that read the first bytes. | Both marks were stripped and the crate still checks clean. The style check now reads the first three bytes of every file it scans and fails on a byte order mark, which was proved by planting one and watching it fire. Its failure label also said `dash(es)` while reporting a mark, which sent the reader looking for a character that was not there, so the label now counts characters. | pass: no source file in any repo carries a byte order mark, and the check that finds one is verified. |
| F29 | The OAuth callback listener served three shipped routes with no request tracing, so a callback left no record anywhere and `CB04` could not be captured on any platform, including WSL. Adding the default HTTP tracing then wrote the live authorization code into the daemon log. | The listener is built and served separately from the API router, and only the API router was given a `TraceLayer`. That is why the WSL pass also recorded `CB04` as capturing no raw status: there was nothing to read. The first repair reused the default span, and `DefaultMakeSpan` records the whole URI. This route's query carries `code` and `state`, so a real 90 character authorization code was written to the log, which is exactly what F7 exists to prevent. | The listener now carries tracing, and its span is built by hand to record method and path only, never the URI. The span builder lives in `routes::providers::callback_span` so it can be tested rather than reviewed. A regression test drives it with a request whose query holds a credential and asserts the route is still identified while the code, the state and the string `code=` are all absent from the log; it was seen red against the URI form, failing with the credential visible in its own message. The capture taken during the leaking build was destroyed rather than filed, and it was never committed. No rotation is needed: an OAuth authorization code is single use and that one had already been exchanged. | pass, and verified end to end on a live credential rather than only in the test: a real owner approval on `e324281` produced `path=/auth/callback status=303` then `path=/auth/complete status=200` in the daemon log, while a scan of that same log for `code=`, `state=` or any query string returned nothing. That closes `CB04`, which had been owed since the WSL pass |

**Findings from the native Linux pass.**

| id | finding | root cause | repair and regression | rerun |
|---|---|---|---|---|
| F31 | The installed cua `shell` tool failed every ordinary call. A run on `gemini-3.5-flash-lite` lost two of its nine iterations to `Error executing tool shell: [Errno 2] No such file or directory: 'uname -a'`, which reads as a missing binary rather than a rejected argument shape. | `shell.run` wrapped a string command in a one element argv list when `shell_mode` was not set, so the kernel looked for a program whose name was the entire command line. Even a bare `uname -a` failed. The tool description said only `run(command, shell_mode=False, ...)`, so the contract could only be discovered by failing. A model that already passed `shell_mode=True` was unaffected, which is why the WSL and Windows passes never saw it: their runs happened to set the flag. | The string is now split into argv the way a command line is split, with no shell involved, so nothing is expanded and no operator is interpreted. A string carrying shell syntax is refused and the message names the operator it found and points at `shell_mode=True`, instead of passing it through as a literal argument. Both the sync and the async paths share one argv builder. Four new cases fail without the fix and were seen red; the full cua suite is 890 passed, 27 skipped. Shipped as cua `0.7.2` on its own branch and PR. | pass, proved over the tool's real MCP wire with a fresh server started from the reinstalled wheel, and then in the product: the re-run of `A13`-`A18` opens with `computer-use__shell {"command": "uname -a"}` carrying no `shell_mode`, it succeeds, the run reports zero errored tool results, and it finished in 5 iterations against 9 before the repair |
| F32 | `POST /api/auth/pair` and `vadgr pair` cannot run on this host. Both refuse with `TRANSPORT_UNREACHABLE`: `Transport cannot advertise a reachable address. Enable Tailscale (VADGR_TRANSPORT=tailscale) to pair over your tailnet.` | Not a defect. The refusal is correct and names its own remedy. The isolated e2e environment binds the loopback transport, and this host has no Tailscale installed, so no reachable address exists to advertise. Installing Tailscale needs an owner account login, which makes it an owner requirement rather than a step the pass can take. | No repair. The requirement is added to the owner and environment table so a later pass schedules it with the other owner-facing work rather than discovering it at the end. | `blocked` on this host: `H04`, `H05`, `H07`, `H08`, `H10` and `K03` need Tailscale on the machine under test. Every other shipped HTTP row, every absence probe and every other CLI row passes here |
| F33 | The written ceiling of six engine iterations was exceeded twice before it was enforced, at 10 and at 9 iterations, and once by one iteration after enforcement was added. | The runbook requires the driver to cancel at any ceiling, and the first Linux group had no cancel wired at all. The poll-based driver added afterwards reads `iterations` from the public run row, so a fast model can pass the ceiling and reach a terminal state inside one poll interval; that is what produced the 7 iteration Gemini run in `A27`, where the cancel arrived after the run had already completed. | The affected runs were re-run with the ceiling enforced and each finished inside it. The token and cost ceilings were never exceeded in any run. A poller cannot guarantee the iteration ceiling; enforcing it exactly needs the product to accept a per-run iteration limit at submission, which does not exist today and is recorded here rather than invented. | recorded, not repaired. Every Linux result now cited finished within its written iteration ceiling |

| F34 | A cancelled run told nobody. The run row reached `cancelled`, and both public sockets went silent: a client that had been watching saw `run_started` and `agent_started` and then nothing, for as long as it stayed connected. Reproduced on a cancel during a provider wait and again on a cancel during an open cua call, so it is every cancellation and not one path. | `RunSupervisor::drive` matches on the engine's outcome. The completed arm emits `agent_completed` and `run_completed`; the failed arm emits `agent_failed` and `run_failed`; the arm for `EngineError::Cancelled` was `{}`. Nothing that reads the run row can see this, which is why `H37`, `H40` and `K23` all pass while the socket says nothing, and why it survived until a pass watched a socket across a cancel. | The cancelled arm now broadcasts `agent_cancelled` and `run_cancelled`, the same shape as its two siblings. `Supervisor::cancel` has already written the row by then, so the arm broadcasts rather than writing again. The phone stream stays silent deliberately: its published types are frozen at `started`, `tool_call`, `output`, `paused`, `completed` and `failed`, and a cancel is a decision rather than a fault, so translating it to `failed` would report the wrong thing. Both names are listed in `NOT_YET_ON_THIS_STREAM` with the reason, so they are classified rather than dropped by fallthrough. A new integration test drives a real run to cancellation and reads the broadcast buffer; it fails without the fix with the exact symptom, carrying only `run_started` and `agent_started`. Two unit tests pin that a cancel never becomes a `failed` frame and that the two published terminals still translate. | pass on the raw socket, proved on the rebuilt release daemon: the same cancel that produced two frames before now produces `run_started`, `agent_started`, `agent_log`, `agent_cancelled`, `run_cancelled`. `C21` is `partial` rather than `pass` because its written oracle asks for both sockets and the phone stream cannot answer without a published vocabulary change. **That change is an owner decision and is not made here**: giving the phone stream a `cancelled` member would let a device tell a cancel from a failure, and today it can only tell that the stream stopped. **Rule 4 applies to this fix.** It changes which frames a cancel puts on the raw socket, so every cell whose evidence names the sockets across a cancel is owed again on the platforms that had passed it: `C21` and `C22` on WSL and on native Windows. Native Linux has re-run both. `C21`'s earlier `pass in surface sweep` is withdrawn outright rather than re-run, because it recorded an exit code and a row status and never captured the sockets its own oracle asks for |

The probe also moved from host networking to a separate BusyBox container that
joins the product container's network namespace. Docker Desktop does not expose
Linux host networking to WSL in the same way as native Linux. The product image
remains `scratch`, and the probe still drives it from outside the product.

## Per-OS results

Legend: `pass` and `fail` mean it ran. `blocked` means it could not run, and
says what stopped it. `not run` means nobody ran it, which is honest and visibly
owed. `Not-Needed` means there is genuinely no OS-specific surface in that part,
and it is only ever written with its reason. **A cell is marked from
observation, never expectation.**

**The automated gate is not an e2e pass.** CI builds an environment and runs the
unit suites. It drives no session, calls nothing over the wire and reaches no
glass, so a green CI row says the suites pass on that OS and nothing about
whether the product works there. The `overall` row never inherits a gate result:
it is the weakest of the parts actually driven on that OS.

**The rows are this runbook's own parts**, so a row can be read back to its
cells. Part B carries its platform in the cell id (`BL` native Linux, `BM`
macOS, `BW` Windows native, `BQ` WSL), and the installed-product cells do the
same (`OS-L`, `OS-M`, `OS-W`, `OS-Q`).

| part | Linux | macOS | Windows native | WSL | notes |
|---|---|---|---|---|---|
| automated gate: build, test, lint | **pass** | **pass (CI)** | **pass (CI)** | **pass** | macOS and Windows are green in CI, and CI is not an e2e pass. WSL ran the four suites locally: engine 122, api 429, cli 152, rust 197, with clippy and fmt clean. Native Linux ran them locally too, on its own host: engine 122, api 432, cli 152, rust 199 with one Docker-only test ignored, plus `fmt`, `check` and `clippy -D warnings` all at exit `0`. The api count moved from 429 because `d5e66a3` added three api tests after the WSL sweep |
| surface coverage: every published endpoint | **pass**, 6 blocked | not run | **pass**, 13 blocked | **pass**, 1 blocked | 25 rows pass on the public boundary. `S12f` is blocked on a missing product path, F21 |
| A: provider onboarding and defaults | **pass**, 29 of 29 | not run | **pass**, 29 of 29 | **pass** | 29 of 29 on both. On Windows all four credential paths pass end to end. The three API-key paths each entered a key without it reaching argv or output, discovered a live authenticated catalog of 51, 28 and 10 models containing the exact selected model, committed one opaque `cred_v1_` record whose value is absent from the database, WAL and SHM, survived a daemon restart, and completed a goal-level tool-using run with an exact independent read-back. `A01` to `A06` completed a real ChatGPT OAuth login through one owner browser approval, returning a seven model account-scoped catalog. `A25` to `A29` connected OAuth and Gemini into one state, kept the OpenAI default across the Gemini commit, ran explicitly on Gemini while OpenAI stayed default, moved the default to Gemini, then deleted OpenAI and left Gemini connected and default |
| B: credential storage and migration | **pass**, 8 of 8 | not run | **pass**, 8 of 8 | **pass** | the eight cases exist per platform as `BL`, `BM`, `BW` and `BQ`. 8 of 8 `BQ` cells pass, including the drvfs root WSL alone can produce. 8 of 8 `BW` cells now pass on a real Windows host, which is where the protected `D:P(A;;FA;;;SY)(A;;FA;;;OW)` descriptor and the junction reparse point are observed rather than argued. Two sub-controls inside `BW05` and `BW06` are owed for want of elevation, and both say so. `BL` and `BM` need their own hosts |
| C: full product path and engine behavior | **pass**, 21 of 25, 4 partial | not run | **pass**, 23 of 25, `C21` and `C22` owed again on `F34` | **pass**, 23 of 25, `C21` and `C22` owed again on `F34` | 25 cells. `C21` and `C22` are owed again on both WSL and native Windows: `F34` changed which frames a cancel puts on the raw socket, and both cells name the sockets in their evidence, so their earlier results describe a build that no longer exists. The host that made the fix has re-run both; the other two re-run them from this branch before merge. Previously 22 pass and 3 partial. `C07` to `C09` park durably and their continuation needs the reply surface that belongs to `0.6.0`. Each row names the run id or commit it was observed on; the section preamble's older rule, that only rows citing `9761f6a` count, no longer matches the rows and is corrected there |
| D: hard-kill restart continuation | **pass**, 7 of 7 | not run | **pass**, 6 of 7 | **pass** | on Windows `D01` to `D05` and `D07` pass after the F27 repair: the marker survives recovery byte-for-byte including its modification time, and the dangling shell action appears exactly once with zero effects. `D06` is not demonstrated, because the resumed run made no external call at all, so no live-state read was observed. That is F28 and it is recorded rather than counted. WSL: 7 of 7 on `ed99bdb`. Killed with `SIGKILL` on an observed durable `in_flight`; both sockets closed at 1006, the restart logged `resumed=1`, the completed effect was untouched, and the first post-restart call was a live-state read |
| E: owner dogfood batch | **pass**, 5 of 5 | not run | **pass**, 5 of 5 | **pass** | 20 of 25. `E04` now records the billed-account figure the owner directed, with the per-run amount `unavailable` for three observed reasons |
| installed product on the host | **pass** (`OS-L`) | not run (`OS-M`) | **pass** (`OS-W`) | **pass** (`OS-Q`) | one cell per platform. `OS-Q` drove Windows Notepad from WSL through the installed cua and survived a restart. `OS-W` now drives Notepad natively on Windows, with an independent desktop capture reading `Ln 2, Col 27` and `40 characters` back. Linux and macOS need their own hosts |
| **overall** | **pass**, 6 blocked, 4 partial | **not run** | **pass**, 1 undemonstrated | **pass**, 2 blocked, 7 partial | every part of this runbook has now been driven on WSL, and each has its own row above. It is not a clean `pass`, and none of the remainder is a WSL defect. `S12f` and `F21` are blocked on a product path that does not exist: `vadgr update` offers no check or dry-run, so the cell cannot run on any host. `C07` to `C09` park correctly and their continuation is re-owned by `0.6.0`'s reply surface. `S01` and `S08f` each observed the whole flow except one upstream-timed portion. `CB04` reached the query-free completion page but captured no raw callback status. `F15` is the boundary correction itself. **Windows native is driven end to end, and it found and fixed three real defects on the way**. Every part has been exercised there and every part passes: all 47 shipped HTTP rows, 30 absence probes, 25 CLI rows, six of seven callback rows, **29 of 29** `A` cells including the full ChatGPT OAuth path and the additive group, **8 of 8** `BW` cells including both controls that needed elevation, **25 of 25** `C` cells, the `D` sequence, **5 of 5** `E` cells and `OS-W`. `D04` and `D05` failed first, were root-caused to recovery rebuilding a resumed conversation as prose rather than as tool-use pairs, were repaired here with a regression test seen red, and now pass. The callback listener had no tracing at all, which is why `CB04` was uncapturable on every platform; it now has tracing whose span records path only, proved by a test that fails with the credential visible. One assertion, `D06`, is not demonstrated and is recorded as F28 rather than counted, and `E03` shows the loop does inspect first when work remains. `CB04` is now closed too, with the raw redirect status captured for the first time in this runbook. **Native Linux is now driven end to end for six of the eight parts, and it found and fixed one real defect on the way.** The gate, the surface sweep, all 29 `A` cells including the live ChatGPT OAuth path and the additive group, all 8 `BL` cells, the whole `D` sequence and `OS-L` pass there. `F31` is the Linux find: the installed cua `shell` tool rejected every ordinary string command, which no earlier platform saw because their runs happened to set `shell_mode`. It is repaired, proved over the tool's own wire and then in the product, and shipped as cua `0.7.2`. Six rows are `blocked` on this host rather than failing: the pairing chain needs Tailscale, which needs an owner account login (`F32`). Parts `C` and `E` are now driven there too: `C` is 21 of 25 with `C07` to `C09` owed by `0.6.0`'s reply surface and `C21` partial on `F34`, and `E` is 5 of 5 against GNOME Text Editor. **`F34` is the second Linux find and it is fixed**: a cancelled run broadcast no terminal frame at all, so a watching client hung while the row read `cancelled`. macOS still has only the automated gate, which is not an e2e pass |

Credential paths, access controls, binary startup, callback binding and child
process launch are platform-shaped. **No supported operating system is
`Not-Needed` for final acceptance.**

**Every part of this runbook is owed on every supported operating system, not
only the one that happened to run first.** The matrix above has a row per part
and a column per OS because each cell is a separate observation, and a part
driven on WSL says nothing about the same part on native Windows, Linux or
macOS. The surface sweep binds sockets and spawns a child process. Part A writes
credential files and reads a platform credential store. Part C spawns the
installed cua child and drives native UI. Part D depends on how the operating
system kills a process and what survives it. Part E opens a native editor. All
five are platform-shaped, so none of them inherits a WSL result.

This was written after a native Windows pass closed the credential group and the
installed-product cell while the other five parts still read `not run` in the
Windows column. That is the honest state to record, and it is also the reason
the `overall` row for an OS is the weakest part actually driven there rather
than the best one.

## What this pass taught, beyond its findings

The Windows execution produced four repaired defects, and it also produced a
list of ways a pass reaches a confident wrong answer. Those are written into
`E2E/TEMPLATE.md` and `E2E/README.md` so the next runbook inherits them instead
of rediscovering them. The short form:

**Nine harness faults each looked exactly like a product failure**, and each was
only resolved by reading the source. A control tool called with the wrong schema
errored instead of parking. The same tool at a risk the default policy
auto-allows approved instead of parking. Attempts were "cancelled" through a
route that does not exist, leaving them pending so two rows tested the wrong
state and one looked like a regression of F7. The callback routes were probed on
the API port when they are served by their own listener. A response body was
parsed after truncation. Six correct refusals were reported as silent because
only `stdout` was counted. A stand-in chose its reply from a global counter
whose parity other runs had shifted. A kill window was missed by polling once a
second. And two daemons leaked from crashed runs held the fixed OAuth port for
hours, which was misdiagnosed as a host condition and even led to a needless
`wsl --shutdown`.

**A self-reported "no secret" check is worthless.** The first callback capture
asserted the query was absent using a test that could never be true, while a
live 90 character authorization code sat in the log beside it. The claim is
verified by grepping the artifact on disk.

**An uncapturable observable was a product gap, not a harness limit.** `CB04`
had been owed since WSL because "no raw callback status was captured". The cause
was that the callback listener had no tracing at all. Fixing that closed the row
on the first attempt, on both platforms' terms.

**Every part is owed on every operating system.** This runbook's per-OS matrix
had a Windows column that was entirely `not run` while six parts read `pass`
from WSL alone. The parts are platform-shaped: sockets, a credential store, a
spawned child, how the OS kills a process, and a native editor.

## What this runbook cannot prove

The written open cells do not yet prove the corrected ChatGPT raw callback redirect-status
capture or the protected valid-key retry; native Linux, macOS or Windows
installed-product sessions; 27 credential-storage cells; 22 engine cells;
11 surface branch cells; a kill inside the owner dogfood batch;
or a monetary cost for ChatGPT OAuth usage. Those cells remain open and prevent
this runbook from declaring the minor fully accepted.

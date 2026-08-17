# 0.4.7 - provider onboarding precedes pairing: e2e runbook

A clean Vadgr installation can connect supported model credentials directly,
keep multiple providers, select one machine default, and complete real work
without an external model CLI in the request path.

> **Status: E2E partially run on WSL, 2026-08-17.** The automated gates and the
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
| B: credential storage | 4 platforms x 8 assertions | 32 | 12 | 20 | 0 |
| OS: installed product | 4 operating systems x 1 full live composition | 4 | 1 | 3 | 0 |
| C: engine behavior | 25 carried native-loop cases | 25 | 25 | 0 | 0 |
| D: restart continuation | 1 sequence x 7 assertions | 7 | 7 | 0 | 0 |
| E: owner dogfood | 1 batch x 5 outcomes | 5 | 5 | 0 | 0 |
| Repeatability | 3 independent passes, each reconciled across 6 observables | 3 | 3 | 0 | 0 |
| Findings | corrections recorded during the pass | 24 | 21 | 1 | 2 |
| | | **260** | **131** | **25** | **104** |

Across the whole runbook the verdicts are 124 `pass`, 7 `partial`, 23 `not run`
and 2 `blocked`. Every `not run` names the host it needs, and both `blocked`
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
| CB01 | `GET /auth/callback?<redacted>` | Owner cancels a pending attempt | `303` to `/auth/failed` | pass |
| CB02 | `GET /auth/callback?<redacted>` | Reuse a callback after its attempt is consumed | `303` to `/auth/failed` | pass |
| CB03 | `GET /auth/callback?<redacted>` | Submit a state that does not match the pending attempt | `303` to `/auth/failed` | pass |
| CB04 | `GET /auth/callback?<redacted>` | Complete a valid live browser authorization | `303` to `/auth/complete` | partial on `b753716`: live browser reached query-free `/auth/complete`; no raw callback response status was captured |
| CB05 | `GET /auth/complete` | Follow CB04 without query parameters | `200`, generic success page | pass |
| CB06 | `GET /auth/failed` | Follow a failed callback without query parameters | `400`, generic failure page | pass |
| CB07 | `GET /auth/callback?<redacted>` | Cancel and clean a pending-attempt fixture | `303` to `/auth/failed`; pending state removed | pass |

The real-TTL expiry remains S01 rather than being treated as another CB row.

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
| BL01 | native Linux | 01 | not run: host required |
| BL02 | native Linux | 02 | not run: host required |
| BL03 | native Linux | 03 | not run: host required |
| BL04 | native Linux | 04 | not run: host required |
| BL05 | native Linux | 05 | not run: host required |
| BL06 | native Linux | 06 | not run: host required |
| BL07 | native Linux | 07 | not run: host required |
| BL08 | native Linux | 08 | not run: host required |
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
| BW05 | Windows native | 05 | not run: the weakened-control fixtures were not built before the session ended. The positive control passes as BW04 |
| BW06 | Windows native | 06 | not run: the unsafe record and reparse-point fixtures were not built before the session ended |
| BW07 | Windows native | 07 | not run: the pre-commit fault fixture was not built before the session ended |
| BW08 | Windows native | 08 | not run: the post-commit fault fixture was not built before the session ended |
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
| OS-L | Native Linux desktop; installed release and cua; fresh state; one owner-supplied provider credential; the documented native text editor is available | Inspect the native OS/session. Open the native text editor, enter the fixed scratch text in an unsaved document, inspect it through the editor UI, restart Vadgr and confirm provider persistence | Health says Linux; real model usage is nonzero; installed cua performs and reads the editor UI effect; journal/API/CLI/both sockets agree; credential controls survive restart | Artifact hash, install command, provider rows, run id/journal/frames, editor UI read-back, restart rows | Close only the test unsaved document without saving; remove isolated state | not run: native Linux host required |
| OS-M | macOS desktop; installed release and cua; fresh state; one owner-supplied provider credential; TextEdit is available | Inspect macOS/session. Open TextEdit, enter the fixed scratch text in an unsaved document, inspect it through the editor UI, restart Vadgr and confirm provider persistence | Health says macOS; live provider and installed cua complete; journal/API/CLI/sockets and editor UI read-back agree; local Application Support controls survive | Same artifacts as OS-L plus macOS ACL/owner metadata | Close only the test unsaved document without saving; remove isolated state | not run: macOS host required |
| OS-W | Native Windows desktop; installed release and cua; fresh state; one owner-supplied provider credential; Notepad is available | Inspect Windows/session. Open Notepad, enter the fixed scratch text in an unsaved document, inspect it through the editor UI, restart Vadgr and confirm provider persistence | Health says Windows; live provider and installed cua complete; journal/API/CLI/sockets and editor UI read-back agree; AppData DACL survives | Same artifacts as OS-L plus Windows DACL/reparse metadata | Close only the test unsaved document without saving; remove isolated state | not run: the host is now prepared and two of its three parts are proved, so what remains is the live run itself. The release daemon serves on this host and reports `platform: windows`, and installed cua `0.7.1` answers over its real stdio wire with 33 tools including the `ui_*` tier. The live model call was not made before the session ended |
| OS-Q | WSL2 release and installed cua with Windows UI reachability; fresh state; OpenAI API key; Windows Notepad is available | Inspect WSL and Windows desktop session. Open Windows Notepad through the Windows UI, enter the fixed scratch text in an unsaved document and inspect it through the Notepad UI. Do not open or save a WSL path. Restart Vadgr and confirm provider persistence | Health says WSL; real usage and installed cua calls complete; Windows editor UI read-back agrees; provider persists with `0700`/`0600` controls | Formal run ids, journals/frames, Notepad UI read-back, provider and credential matrix | Close only the test unsaved document without saving; stop only the isolated daemon | pass on `ed99bdb`: `run-67087e98a8964990a511da089a58c4f0` completed in 1 m 10 s over 19 model responses, under the 20 ceiling, using 173,143 input and 725 output tokens on `gpt-5.6-sol`. Health reported `platform: wsl` with `computer_use: true`. The journal records the real cross-OS sequence through the installed cua: `get_platform_info`, screenshot, `win`, screenshot, `type_text Notepad`, screenshot, `enter`, a 2 s wait, screenshot, `type_text` of the two fixed lines, a full screenshot, then `screenshot_region` over the Notepad text area, which is the UI read-back oracle. No filesystem or application-open tool was called at all, so nothing was opened, created or saved and no WSL path was touched. Independent oracle: a separate capture of the Windows desktop shows Notepad holding exactly `Vadgr dogfood` and `Verified through editor UI`, with an unsaved marker on its tab and its own status bar reading `Ln 2, Col 27` and `40 characters`. After stopping only the assigned pid and restarting the same state, the provider persisted: OpenAI stayed connected and default on the identical reference `cred_v1_f72e8f0c...`, the directory stayed `0700` and the record stayed `0600`, and the run row still served 200. |

## Part C: full product path and engine behavior

Every row here names the run id, commit or released artifact it was observed on,
and that attribution is the row's provenance. An earlier version of this
paragraph said only rows citing `9761f6a` were E2E results, which stopped being
true as cells were re-run at later commits: `C02` was observed at `21f6078`,
`C14`, `C15` and `C17` were re-run against a deterministic provider fixture with
their run ids recorded, and `C22` was re-run against released cua `0.7.1`. Read
each row's own attribution rather than a single commit named here.

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
| C21 | Model request active and no cua call yet open | Cancel through API/CLI | Provider wait is cancelled; row and both sockets say cancelled; no retry or later completion overwrites it | Timing marker, HTTP/CLI, DB, sockets, journal | None | pass in surface sweep |
| C22 | Long cua call recorded `in_flight` and cancellable | Cancel through API/CLI while the child call is open | Call and run cancel promptly; no terminal `done` appears after cancellation; child cleanup is bounded | Timing marker, process tree, journal, DB, sockets | Remove reversible effect; stop child if owned | pass on WSL with installed CUA `0.7.1`: terminal `vadgr runs cancel` made `run-c6774f9e832c4479b13021f2591c7b96` cancelled with no journal `done` and no owned `sleep 30` process after five seconds. Native-OS reruns remain open. |
| C23 | Computer use enabled and installed cua executable present | Probe status, then run a cua-requiring goal | Status is available and run dispatches through installed cua | Settings/status, process argv, journal and read-back | Stop owned child | pass on `9761f6a`: public status and installed-cua journal calls agree |
| C24 | Computer use disabled before run | Probe status and start a goal that would require cua | Status is disabled; cua is not spawned; run receives the named unavailable path rather than silently acting | Settings/status, process snapshot, run/journal/sockets | Restore enabled setting | pass on `21f6078`: public status was unavailable; a CUA-requesting run failed `NO_ACTION_TAKEN` after the model received the unavailable surface, and no CUA process started. |
| C25 | Computer use enabled but configured runtime absent | Probe status and start a cua-requiring goal | Status is unavailable with named reason; no child starts; run fails or reacts through the published error path | Status body, process snapshot, run/journal/sockets | Restore runtime path | pass on `21f6078`: an absent configured executable produced unavailable status, no child process and the named no-action failure path. |

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

| id | trigger/action | expected observable and oracle | evidence boundary | status |
|---|---|---|---|---|
| D01 | Wait until the marker is readable and its creating cua call is durably `in_flight`, then send `SIGKILL` only to the assigned daemon PID | Process exits without graceful completion; DB remains running; both sockets close abnormally | PID, process/port snapshot, marker metadata, pre-kill journal and socket closes | pass on `ed99bdb`: the kill landed at an observed moment rather than a guessed one. The harness waited until the completed effect `marker-effect.txt` was readable and one `computer-use__shell` call was durably `in_flight` with no matching `done`, then sent `SIGKILL` to the one assigned pid. The process exited without graceful completion, the port stopped serving, and the database file remained. Both public sockets closed abnormally at code 1006, the raw one and the mobile one alike. The uncertain action's own effect file was still absent at the kill boundary, and the orphaned shell child did not survive the daemon, so that effect never occurred at all. |
| D02 | Restart the same release with identical database, state and journal roots | Same run resumes automatically from the next journal sequence, with no owner resume request | Restart log, health, run id and first post-restart sequence | pass on `ed99bdb`: restarting the same release on the identical database, state and run roots resumed the same run by itself. The daemon logged `run recovery scan complete resumed=1 parked=0 failed=0`, and no owner resume request was made. |
| D03 | Compare journal prefix before kill with final journal | Prefix is byte-identical and sequence increases monotonically in the same file | Pre/final journal hashes and sequence report | pass on `ed99bdb`: the journal kept before the kill and the same prefix of the final journal share one `sha256`, so the prefix is byte-identical, and the run continued in the same file rather than a new one. The sequence numbers increase without ever going backwards across the kill boundary. |
| D04 | Compare completed marker effect before and after recovery | Completed side effect is not repeated; inode, modification time, hash and content are unchanged | Marker metadata/read-back before and after | pass on `ed99bdb`: the completed side effect was not repeated. After recovery `marker-effect.txt` carries the same inode, the same modification time, the same size, the same `sha256` and the same contents `partd-marker-20260817` recorded at the kill boundary. |
| D05 | Count the dangling shell action across final journal/process evidence | Boot does not blindly redispatch it; the shell effect appears once | Tool sequence/count and process record | pass on `ed99bdb`: boot did not blindly redispatch the dangling call. The killed `computer-use__shell` entry at sequence 1 was never re-issued by the daemon, and the effect it would have produced appears zero times, which matches the shell child having died with the daemon. |
| D06 | Inspect the first post-restart external call | Live-state read occurs before any decision to retry the uncertain action | Ordered post-restart tool records | pass on `ed99bdb`: the first external call after the restart was a live-state read, not a retry. The loop wrote a todo reading `Inspect live state of uncertain-effect command; do not replay`, then called `computer-use__fs` with `op: stat` on the uncertain effect's path, which returned an error because the file was absent. Only after that did it report `The expected output file is not present yet` and wait. The read came before any decision about the uncertain action. |
| D07 | Let the resumed run terminate and reconcile every surface | Database, API, journal and both sockets agree on completed status and usage; restored todos accept later updates | Final API/DB rows, raw/mobile terminal frames, journal/usage and todo report | pass on `ed99bdb`: the resumed run terminated `completed` and every surface agrees. The database row, the public `GET /api/runs/<id>` and the journal all report `completed` with 81,959 input and 1,108 output tokens, and the public `vadgr runs list` shows the same run. The journal's sequence numbers never go backwards across the kill. Both public sockets reach their terminal frame, the raw one with `completed` and the mobile one with `run_completed`; the mobile stream also carries a `run_resumed` frame, which is the resume itself observed on the wire rather than inferred. Restored todos accepted later updates: three `todos` frames follow the restart. |

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

| F24 | The mandatory credential gate could not pass on native Windows, and had never run there at all. Preparing the Windows host was the first time anyone invoked it with `--env-file` on that platform. | `scripts/check_no_secrets.py` passed the target path as a trailing argument to `powershell.exe -Command`. PowerShell does not bind `$args` under `-Command`; it appends the remaining tokens to the command text instead. `$args[0]` was therefore always empty, `Get-Acl` received nothing, and the check failed closed on every file it was given. The gate reported `the local environment file must have an owner-only Windows DACL` whatever the real DACL was, so a correctly protected file and a world-readable one were indistinguishable. Two things hid it: CI runs the gate only on `ubuntu-latest` and never passes `--env-file`, so the Windows branch executed nowhere, and the gate had no test of its own on any platform. | The target now reaches PowerShell through an environment variable, which also keeps a path containing spaces or quotes out of the parser. Four tests cover it: the invocation contract, the script shape, a real accept and refuse round trip that grants a broad `S-1-5-11` entry through `icacls`, and a missing-target fail-closed. All four were seen red against the reverted script, and the gate itself was seen refusing the same correctly protected file. A new `gate-tests` job runs them on `ubuntu-latest` and `windows-latest`, because the defect survived precisely by having no test and one operating system. | pass: the gate returns `SECRET CHECK PASSED` against the owner-only workspace `.env` on native Windows 11 |

| F25 | `vadgr-cua doctor` cannot run on native Windows, which blocks the handoff step that requires recording it. | `computer_use/bridge/supervisor.py:22` imports `fcntl`, which is Unix only. The docstring on `_get_supervisor` at `computer_use/mcp_server.py:866` states the intent correctly: the supervisor must not load on native Windows, and only the daemon subcommands need it. `_cmd_doctor` at line 902 then calls `_get_supervisor().status()` unconditionally, so the code contradicts its own comment and the command dies before it can print anything. | Not repaired here, because the defect is in the computer-use repository rather than this one, and a patch there implies its own release. The verdict was probed rather than assumed: the installed `0.7.1` wheel was driven over its real stdio wire with an `initialize` and `tools/list` exchange, and it returned **33 tools** including the whole `ui_*` structured tier. So the hot path the daemon actually spawns is healthy and only the `doctor` subcommand is broken. The stdio probe is filed with the evidence and is the stronger oracle, because it exercises the wire a client uses rather than a status helper. | pass for the wire, blocked for `doctor`: the Windows cells that need the tool surface can proceed on the probe |

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
| automated gate: build, test, lint | **pass (CI)** | **pass (CI)** | **pass (CI)** | **pass** | all three OS rows are green in CI, and CI is not an e2e pass. WSL ran the four suites locally: engine 122, api 429, cli 152, rust 197, with clippy and fmt clean |
| surface coverage: every published endpoint | not run | not run | not run | **pass**, 1 blocked | 25 rows pass on the public boundary. `S12f` is blocked on a missing product path, F21 |
| A: provider onboarding and defaults | not run | not run | not run | **pass** | 29 of 29. Four provider paths onboarded, catalogs discovered, defaults committed |
| B: credential storage and migration | not run | not run | **partial**, 4 of 8 | **pass** | the eight cases exist per platform as `BL`, `BM`, `BW` and `BQ`. 8 of 8 `BQ` cells pass, including the drvfs root WSL alone can produce. `BW01` to `BW04` now pass on a real Windows host, which is where the protected `D:P(A;;FA;;;SY)(A;;FA;;;OW)` descriptor is observed rather than argued. `BW05` to `BW08` are owed on that host. `BL` and `BM` need their own hosts |
| C: full product path and engine behavior | not run | not run | not run | **pass**, 3 partial | 25 cells, 22 pass and 3 partial. `C07` to `C09` park durably and their continuation needs the reply surface that belongs to `0.6.0`. Each row names the run id or commit it was observed on; the section preamble's older rule, that only rows citing `9761f6a` count, no longer matches the rows and is corrected there |
| D: hard-kill restart continuation | not run | not run | not run | **pass** | 7 of 7 on `ed99bdb`. Killed with `SIGKILL` on an observed durable `in_flight`; both sockets closed at 1006, the restart logged `resumed=1`, the completed effect was untouched, and the first post-restart call was a live-state read |
| E: owner dogfood batch | not run | not run | not run | **pass** | 20 of 25. `E04` now records the billed-account figure the owner directed, with the per-run amount `unavailable` for three observed reasons |
| installed product on the host | not run (`OS-L`) | not run (`OS-M`) | not run (`OS-W`) | **pass** (`OS-Q`) | one cell per platform. `OS-Q` drove Windows Notepad from WSL through the installed cua and survived a restart. The other three need their own hosts |
| **overall** | **not run** | **not run** | **partial** | **pass**, 2 blocked, 7 partial | every part of this runbook has now been driven on WSL, and each has its own row above. It is not a clean `pass`, and none of the remainder is a WSL defect. `S12f` and `F21` are blocked on a product path that does not exist: `vadgr update` offers no check or dry-run, so the cell cannot run on any host. `C07` to `C09` park correctly and their continuation is re-owned by `0.6.0`'s reply surface. `S01` and `S08f` each observed the whole flow except one upstream-timed portion. `CB04` reached the query-free completion page but captured no raw callback status. `F15` is the boundary correction itself. **Windows native stops being a bare `not run`**: the release daemon was built and driven on a real Windows 11 host, `BW01` to `BW04` pass there, and health reports `platform: windows`. It is `partial` and not `pass`, because `BW05` to `BW08` and `OS-W` are owed on that host. Linux and macOS still have only the automated gate, which is not an e2e pass |

Credential paths, access controls, binary startup, callback binding and child
process launch are platform-shaped. **No supported operating system is
`Not-Needed` for final acceptance.**

## What this runbook cannot prove

The written open cells do not yet prove the corrected ChatGPT raw callback redirect-status
capture or the protected valid-key retry; native Linux, macOS or Windows
installed-product sessions; 27 credential-storage cells; 22 engine cells;
11 surface branch cells; a kill inside the owner dogfood batch;
or a monetary cost for ChatGPT OAuth usage. Those cells remain open and prevent
this runbook from declaring the minor fully accepted.

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
> **18 findings: F15 corrected the E2E boundary and F16 passed its bounded
> rerun. F17's valid-monitor rerun is blocked by OpenAI quota exhaustion after
> 14 responses. F19's installed CUA 0.7.1 fix passed the WSL cancellation
> rerun; its native-OS reruns remain open. Untouched cells remain open below.**

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
| native Linux desktop host | BL01-BL08, OS-L | release artifact and installed cua are present on a non-WSL Linux desktop | creates isolated state and reversible test files | remove only the isolated state and test files |
| macOS host | BM01-BM08, OS-M | release artifact and installed cua are present on macOS | creates local Application Support state and reversible test files | remove only the isolated state and test files |
| Windows native host | BW01-BW08, OS-W | release artifact and installed cua are present in native Windows | creates local AppData state and reversible test files | remove only the isolated state and test files |
| WSL2 plus Windows desktop applications | BQ01-BQ08, OS-Q, E01-E05 | installed cua can reach the Windows UI from WSL | opens applications and creates reversible files | delete test files; do not terminate unrelated applications |
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
The owner dogfood has a separate ceiling because opening, writing and saving a
Windows application from WSL requires several grounded UI turns. It is not a
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
   `python3 scripts/check_no_secrets.py --env-file ../.env` before testing.
3. Build the release with `cargo build --locked --release --manifest-path
   rust/Cargo.toml`. Copy the resulting `vadgr-daemon` or `vadgr-daemon.exe`
   into an empty host-local test root and run that copy. Never use `cargo run`
   as the product under test.
4. Create a fresh Python virtual environment inside that test root. Install
   `vadgr-computer-use==0.7.0`, record `vadgr-cua doctor`, and set
   `VADGR_CUA_BIN` to that installed executable. On Linux, run
   `vadgr-cua install-deps --yes`. On macOS, grant Accessibility and Screen
   Recording to that environment's Python. On Windows, keep the test native;
   do not route it through WSL.
5. Create the evidence directory before the first cell. Record only the commit,
   artifact hashes, tool versions, redacted commands, status codes, structured
   responses, access-control metadata, journals, socket frames and independent
   read-backs. Do not record environment values, authorization headers, callback
   queries or unredacted screenshots that contain them.
6. Run the platform's eight credential cells in order: `BL01`-`BL08`,
   `BM01`-`BM08` or `BW01`-`BW08`. Then run `OS-L`, `OS-M` or `OS-W`. Preserve
   state only where the next cell names it as a precondition. Use a new state
   root for every unrelated group.
7. Run the secret check again before the evidence boundary is sealed. Remove
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
| required GitHub Actions jobs | not run |

The automated tests prove deterministic state, protocol, migration, and error
cases. They cannot prove an external account can authenticate, a live model can
act through installed cua, or a killed installed daemon can continue safely.

## Coverage

There are no deferrals from this minor. The `0.4.6` provider-blocked close is
carried here in full and is part of acceptance.

| Part | Axes | Cells | Run | Open |
|---|---|---:|---:|---:|
| Surface inventory | 47 HTTP + 7 callback + 25 CLI + 22 branch cells | 101 | 90 | 11 |
| A: onboarding | 4 credential paths x 6 assertions + 5 additive/default cells | 29 | 29 | 0 |
| B: credential storage | 4 platforms x 8 assertions | 32 | 1 | 31 |
| OS: installed product | 4 operating systems x 1 full live composition | 4 | 0 | 4 |
| C: engine behavior | 25 carried native-loop cases | 25 | 3 | 22 |
| Repeatability | 3 independent passes, each reconciled across 6 observables | 3 | 2 | 1 |
| D: restart continuation | 1 sequence x 7 assertions | 7 | 0 | 7 |
| E: owner dogfood | 1 batch x 5 outcomes | 5 | 0 | 5 |
| | | **206** | **125** | **81** |

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
| S06 | Passing connected provider and captured catalog; upstream then made unreachable without changing local state | Request catalog refresh through API and CLI | Refresh fails with the named error; previous credential, catalog and default remain unchanged | Status/code/body, CLI exit/output, before/after DB rows and filenames | Restore network; refresh once | not run |
| S07 | Two connected providers; captured current default; candidate provider then made unreachable | Request the candidate as default | Readiness fails; old default remains; neither credential nor catalog changes | Status/code/body, before/after default and provider rows | Restore network | not run |
| S08a | Fresh state; interactive terminal | Run `vadgr provider login` with no provider argument | Provider chooser shows OpenAI, Gemini, Anthropic once and accepts one selection | TTY transcript and zero provider mutation before selection | Cancel before credentials | pass on `9761f6a`: terminal chooser showed all three providers |
| S08b | OpenAI selected in an interactive terminal | Continue without preselecting a method | Exactly `Continue with ChatGPT` and `OpenAI API key` are offered; cancellation returns without mutation | TTY transcript, provider rows | Cancel and remove attempt | pass on `9761f6a`: both methods appeared once; cancellation left provider JSON byte-identical |
| S08c | Fresh state and owner-supplied OpenAI API key | Complete `vadgr provider login openai --auth api-key` | Hidden entry, live catalog, readiness, immutable credential and successful return; no pairing | CLI transcript without secret, usage, rows, file metadata | Logout and unset key | pass on `9761f6a`: terminal onboarding, live readiness, immutable commit and restart persistence passed |
| S08d | Fresh state and owner-supplied Gemini API key | Complete `vadgr provider login gemini` | No redundant method screen; hidden entry, live catalog/readiness, immutable credential; no pairing | CLI transcript without secret, usage, rows, file metadata | Logout and unset key | pass on `9761f6a`: terminal onboarding, live readiness, immutable commit and restart persistence passed |
| S08e | Fresh state and owner-supplied Anthropic API key | Complete `vadgr provider login anthropic` | No redundant method screen; hidden entry, live catalog/readiness, immutable credential; no pairing | CLI transcript without secret, usage, rows, file metadata | Logout and unset key | pass on `9761f6a`: terminal onboarding, live readiness, immutable commit and restart persistence passed |
| S08f | Interactive login with one deliberately rejected credential followed by a valid owner-supplied credential | Retry through the CLI recovery path | Error is named, input remains hidden, no failed candidate commits, and valid retry succeeds once | CLI exit/output, attempts, rows, filenames before/after | Logout and unset key | partial on `c990dd2`: public terminal invalid-key entry produced the named error and retry menu with zero provider/default mutation. The protected valid-key retry remains open because the automated PTY cannot safely deliver a secret after the interactive recovery prompt. |
| S09 | Fresh state, OpenAI OAuth account, callback port free | Run one uninterrupted `vadgr provider login openai --auth chatgpt` command through browser approval | The same command returns `0` only after readiness and commit; no manual API call completes it | Full CLI transcript, callback redirect, readiness usage, committed rows | Remove isolated state | pass on `9761f6a`: the public command opened the browser, completed readiness and committed the connection before exit `0` |
| S10 | At least two available models; interactive terminal; captured old default | Run `vadgr model default` with no model argument and select a different model | Chooser contains the authenticated union; readiness passes before exactly one default changes | TTY transcript, usage, before/after default | Restore original default | pass on `9761f6a`: 89 authenticated models appeared; Gemini became the sole default after readiness; terminal `vadgr` restored OpenAI |
| S11 | Fresh state with no default | Run `vadgr pair`, choose a provider and authenticate | Successful readiness commits the initial default and continues directly to QR without another question | TTY transcript, usage, rows, pair response | Revoke pair; remove state | pass on `c990dd2`: the S02 fresh state committed the initial OpenAI default before the first QR; the pair command did not ask a second provider or model question. |
| S12a | Installed release; isolated service stopped; known service name | Run `vadgr start` | Service starts on configured port; health is ready; command output names the real endpoint | CLI transcript, process/service record, health, daemon log | Continue to S12b | not run |
| S12b | Service started by S12a | Run `vadgr api` | Alias reaches the same installed daemon and prints nonempty output; it does not start a second daemon | CLI transcript, PID/port snapshot, health | None | not run |
| S12c | Healthy service and active socket capture | Run `vadgr restart` | Old PID exits, port is released, new PID becomes healthy, persisted providers remain | CLI transcript, PID/port snapshots, provider rows, log | Continue to S12d | not run |
| S12d | Healthy restarted service | Run `vadgr logs` | Output is nonempty and belongs to the isolated service instance | CLI transcript and matching daemon-log markers | None | not run |
| S12e | Healthy isolated service | Run `vadgr stop` and wait for port release | Command returns only with service stopped or the harness verifies release; health then fails with exit `3` | CLI transcript, service state, port snapshot, health exit/output | Restore initial stopped state | not run |
| S12f | Installed release and owner-approved update preflight; no unapproved installation mutation | Run the documented update check or dry-run path | Current/new version and intended artifact are reported; no source-tree execution and no install mutation without explicit approval | CLI transcript, version before/after, filesystem manifest | Restore only if an approved update ran | not run |

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
| BW01 | Windows native | 01 | not run: host required |
| BW02 | Windows native | 02 | not run: host required |
| BW03 | Windows native | 03 | not run: host required |
| BW04 | Windows native | 04 | not run: host required |
| BW05 | Windows native | 05 | not run: host required |
| BW06 | Windows native | 06 | not run: host required |
| BW07 | Windows native | 07 | not run: host required |
| BW08 | Windows native | 08 | not run: host required |
| BQ01 | WSL | 01 | pass on `c990dd2`: public CLI and direct health API agreed on a fresh schema-v1 database with no provider, catalog or default rows. |
| BQ02 | WSL | 02 | acceptance observation only with real `0.4.6` database; corrected E2E not run |
| BQ03 | WSL | 03 | acceptance observation only; corrected E2E not run |
| BQ04 | WSL | 04 | acceptance observation only; corrected E2E not run |
| BQ05 | WSL | 05 | acceptance observation only; corrected E2E not run |
| BQ06 | WSL | 06 | acceptance observation only; corrected E2E not run |
| BQ07 | WSL | 07 | acceptance observation only; corrected E2E not run |
| BQ08 | WSL | 08 | acceptance observation only; corrected E2E not run |

## Installed product on every supported operating system

The earlier OS-Q row is a superseded acceptance observation. The corrected E2E
status of every OS cell is `not run`.

These cells use a release artifact installed on that host, a real supported
provider connection and the installed cua child. Compilation or a fake-provider
credential matrix cannot substitute for them.

| id | precondition and setup | goal | expected observable and oracle | evidence boundary | cleanup | status |
|---|---|---|---|---|---|---|
| OS-L | Native Linux desktop; installed release and cua; fresh state; one owner-supplied provider credential | Inspect the native OS/session, create a reversible file through cua, read it back, restart Vadgr and confirm provider persistence | Health says Linux; real model usage is nonzero; installed cua performs the effect; journal/API/CLI/both sockets agree; credential controls survive restart | Artifact hash, install command, provider rows, run id/journal/frames, read-back, restart rows | Delete file and isolated state | not run: native Linux host required |
| OS-M | macOS desktop; installed release and cua; fresh state; one owner-supplied provider credential | Inspect macOS/session, create and read a reversible file through cua, restart and confirm persistence | Health says macOS; live provider and installed cua complete; journal/API/CLI/sockets and file read-back agree; local Application Support controls survive | Same artifacts as OS-L plus macOS ACL/owner metadata | Delete file and isolated state | not run: macOS host required |
| OS-W | Native Windows desktop; installed release and cua; fresh state; one owner-supplied provider credential | Inspect Windows/session, create and read a reversible file through cua, restart and confirm persistence | Health says Windows; live provider and installed cua complete; journal/API/CLI/sockets and file read-back agree; AppData DACL survives | Same artifacts as OS-L plus Windows DACL/reparse metadata | Delete file and isolated state | not run: native Windows host required |
| OS-Q | WSL2 release and installed cua with Windows UI reachability; fresh state; OpenAI OAuth | Inspect WSL and Windows desktop session, perform a reversible WSL/Windows UI task, read back from WSL and restart | Health says WSL; real usage and installed cua calls complete; Windows UI and WSL read-back agree; provider persists with `0700`/`0600` controls | Formal run ids, journals/frames, dogfood read-back, provider and credential matrix | Test file removed; isolated daemon stopped | acceptance observation only; corrected E2E not run |

## Part C: full product path and engine behavior

Rows that cite corrected provider evidence at `9761f6a` are E2E results. Other
statuses remain superseded acceptance observations only.

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
| C14 | Provider fixture returns `end_turn` before any completed tool | Start through API and CLI | Run fails `NO_ACTION_TAKEN`; zero effects; raw/mobile terminal failure agrees with DB/journal | Fixture identity, run row, journal, both sockets, CLI exit | Remove fixture state | not run |
| C15 | Provider fixture returns `max_tokens` without a tool | Start through API and CLI | Run fails as truncated, never completes, and performs zero effects | Run row/error, response/journal, sockets, CLI | Remove fixture state | not run |
| C16 | Accepted run whose selected provider fails before or during model completion | Start and observe failure; manually resume only after row is failed | Named provider failure reaches DB, CLI and sockets; no fabricated usage/effect; old credentials remain | HTTP/CLI, run row, sockets, journal, provider rows | Restore provider reachability | pass in surface sweep |
| C17 | Deterministic provider fixture emits valid nonterminal turns until limit | Start through API and CLI | Exactly the configured iteration limit is attempted, then named terminal failure with no extra provider call | Provider request count, journal iterations, DB/sockets/CLI | Remove fixture state | not run |
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

## Repeatability - three independent acceptance passes

Three agents used separate ports, databases, state roots, run roots, daemons,
installed terminal commands and provider attempts. R02 and R03 pass. R01 fails
because the valid actively guarded attempt reached the six-response ceiling
before reading the marker. Failed monitor attempts are retained rather than
substituted for the decisive result.

| id | corrected pass requirement | result |
|---|---|---|
| R01 | Agent A uses its own port, database, state, runs, daemon and terminal `vadgr`; reconcile HTTP, CLI, raw socket, mobile socket, journal and usage | fail: guarded attempt cancelled at response 6 before marker read-back; 34,610 input / 404 output |
| R02 | Agent B runs the identical fixture concurrently with R01 and R03 under its own isolated resources | pass: exact marker in 4 responses; 22,466 input / 176 output; all surfaces agree |
| R03 | Agent C runs the identical fixture concurrently with R01 and R02 under its own isolated resources | pass: exact marker at response 6; 34,436 input / 346 output; terminal cancel raced completed state; no seventh response |

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

## Part D: hard-kill restart continuation

The rows below are superseded acceptance observations. The corrected E2E result
for D01-D07 is `not run`.

The group starts from one connected provider, installed cua, a fresh DB/state/
runs root, both sockets attached, a reversible marker absent, and the exact
assigned daemon PID recorded. It captures at the kill boundary and again at
terminal completion, then removes the marker and stops only its own daemon.

| id | trigger/action | expected observable and oracle | evidence boundary | status |
|---|---|---|---|---|
| D01 | Wait until the marker is readable and its creating cua call is durably `in_flight`, then send `SIGKILL` only to the assigned daemon PID | Process exits without graceful completion; DB remains running; both sockets close abnormally | PID, process/port snapshot, marker metadata, pre-kill journal and socket closes | pass: kill occurred at sequence 6 |
| D02 | Restart the same release with identical database, state and journal roots | Same run resumes automatically from the next journal sequence, with no owner resume request | Restart log, health, run id and first post-restart sequence | pass: same run resumed from sequence 7 |
| D03 | Compare journal prefix before kill with final journal | Prefix is byte-identical and sequence increases monotonically in the same file | Pre/final journal hashes and sequence report | pass |
| D04 | Compare completed marker effect before and after recovery | Completed side effect is not repeated; inode, modification time, hash and content are unchanged | Marker metadata/read-back before and after | pass |
| D05 | Count the dangling shell action across final journal/process evidence | Boot does not blindly redispatch it; the shell effect appears once | Tool sequence/count and process record | pass |
| D06 | Inspect the first post-restart external call | Live-state read occurs before any decision to retry the uncertain action | Ordered post-restart tool records | pass: marker read was first |
| D07 | Let the resumed run terminate and reconcile every surface | Database, API, journal and both sockets agree on completed status and usage; restored todos accept later updates | Final API/DB rows, raw/mobile terminal frames, journal/usage and todo report | pass |

The final rerun used source `5558cf6` and run
`run-6889e6bf31e44e309114f8c9ffe7078b`. It also proved that the reconstructed
todo list survived restart and accepted both subsequent updates.

## Part E: owner dogfood batch

The rows below are superseded acceptance observations. The corrected E2E result
for E01-E05 is `not run`.

| id | precondition and setup | goal or trigger | expected observable and oracle | evidence boundary | cleanup | status |
|---|---|---|---|---|---|---|
| E01 | Installed release, OpenAI OAuth, installed cua, isolated WSL state, Windows Notepad available | From the CLI, create a WSL file, open it through Windows Notepad, append and save a second line, then verify from WSL | One run reaches completed after real cross-OS work; exact two-line read-back matches | CLI, run row, journal, sockets, file hash/content and UI action records | Delete file; leave unrelated Notepad processes untouched | blocked on `c54544b` with CUA `0.7.1`: valid monitored `run-29e7554250f94c218ce6fd1904d7b47d` reached 14 responses, opened the test file in Windows Notepad, then OpenAI returned provider quota exhausted before the append/read-back. |
| E02 | E01 setup and reversible target | Let the model choose cua as hands for every machine action | No direct operator mutation substitutes for cua; every external action is countable and independently read back | Journal tool sequence, boundary audit and exact file read-back | Delete reversible target | blocked with E01: the provider failed before final read-back. |
| E03 | Owner approves assigned daemon PID and reversible marker; same owner-work goal as E01; both sockets attached before start | After at least one completed effect, kill only the assigned daemon with `SIGKILL` while a later cua call is durably `in_flight`; restart same state and let the batch finish | Same run continues; journal prefix and todos survive; live-state inspection precedes any retry; completed effect occurs once; final Notepad/WSL read-back is exact | PID/kill point, pre/post journal, marker metadata, DB/API, both sockets, final work read-back | Remove marker and owner-work file; stop only assigned daemon | not run: owner permission required; Part D alone does not close this cell |
| E04 | Completed E01 or E03 run plus an authoritative provider response, billed-account usage record or owner-approved pricing rule | Reconcile run usage to elapsed time, model calls, input/output tokens and monetary amount | Record names source and currency and either an exact amount or an owner-approved `unavailable` disposition; no guessed subscription price | Run metrics, provider/account record with secrets removed, calculation and disposition | Remove any sensitive account capture after redacted facts are filed | partial: 86.080s, 22 calls, 1,628,437/1,050 tokens; money source missing |
| E05 | E01 or E03 complete | Count every approval, question and other human intervention from channel records | Exact contact count and reasons reconcile with journal `await_user` records | Channel record, journal count and summary | None | pass for E01: zero contacts |

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
| F13 | The additive preflight tried OpenAI Platform API-key authentication although A25 specifies ChatGPT OAuth plus Gemini API key. | The executable harness encoded a provider combination that differed from the approved cell even though both used the OpenAI provider id. | The harness now invokes the ChatGPT OAuth method and pins the proven general Gemini model from the authenticated catalog. | not rerun: the corrected flow requires owner browser approval |
| F14 | Provider-neutral E2E work used expensive product starters without a dated model comparison or hard spend ceiling. | The runbook declared that credentials were billed but did not require capability/price research, an explicit cost-effective engine model, or cancellation thresholds; the harness inherited the provider default. | Shared engineering, both machine-side entry points and both E2E templates now require current official research, authenticated-catalog validation, explicit cheapest-capable models, bounded iteration/token/money ceilings and evidence-based escalation. This runbook selects Luna, Flash-Lite and Haiku for future generic engine work. | not rerun: the next authorized billed group must prove its driver cancels at the written ceiling |
| F15 | The WSL evidence called `python -m cli` from Python drivers while the runbook claimed the shipped terminal CLI. | The capture scripts replaced the public `vadgr` entry point. The review treated real daemon and wire activity as sufficient although the on-box user surface was bypassed. | Shared engineering, both machine-side entry points and both E2E templates now require the public command. This runbook reclassifies every affected live result as an acceptance diagnostic. | partial pass: API-key onboarding, three provider runs, 47 shipped HTTP rows, 30 absence probes, 25 CLI rows and six callback rows now use the corrected public boundary; remaining cells stay open |
| F16 | The corrected Gemini Flash-Lite run completed and matched its read-back, but used seven model iterations against the written six-iteration ceiling. | Foreground `vadgr run` watched the product outcome but no independent guard cancelled the run at the cost boundary. | Keep the six-iteration ceiling. The corrected rerun starts through terminal `vadgr`; a capture-only monitor invokes public `vadgr runs cancel` when the sixth response is durable. | pass: bounded `run-19fa499edbf94542b5d7b4321447d597` completed in two turns before cancellation, with 15,499 input, 106 output and exact read-back |
| F17 | The WSL/Windows dogfood attempt reached 27 responses although its monitor reported zero. | The monitor matched a spaced JSON form while the live JSONL used compact `"phase":"response"`; a second ad-hoc monitor was also not a valid pre-acceptance guard. | The 27-response attempt is invalid evidence. Every future bounded cell uses a pre-armed, JSON-aware monitor whose recorded count is checked against the journal before verdict. | partial: the final retry's foreground monitor recorded 14 responses correctly, but OpenAI quota exhaustion blocked completion. |
| F19 | Cancelling a live CUA shell call ended the Vadgr run but did not terminate the shell child. | Cancellation stopped the Rust dispatch future and later closed the CUA server, but the CUA child process was not cancellation-aware. | CUA `0.7.1` runs `shell.run` asynchronously, terminates its Unix process group or Windows process tree on cancellation, and has a focused regression. | partial: the final installed-wheel WSL rerun cancelled cleanly with no child after five seconds. Linux, macOS and Windows native reruns, plus the owner dogfood rerun, remain required. |

The probe also moved from host networking to a separate BusyBox container that
joins the product container's network namespace. Docker Desktop does not expose
Linux host networking to WSL in the same way as native Linux. The product image
remains `scratch`, and the probe still drives it from outside the product.

## Per-OS results

Legend: pass / fail / blocked / not run / **Not-Needed**.

| | Linux | macOS | Windows native | WSL |
|---|---|---|---|---|
| build, test, and lint | CI not run | CI not run | CI not run | pass locally |
| credential matrix | not run | type check only | type check only | not run for E2E; prior acceptance diagnostics retained |
| clean install | pass in Linux `scratch` | not run | not run | driver host only |
| live providers | not run | not run | not run | partial: three API-key paths and ChatGPT OAuth onboarding/work/browser page pass; coexistence, replacement, deletion, stale catalog and pairing-first pass; expired callback redirect and protected retry remain open |
| full engine | not run | not run | not run | partial: OpenAI Platform, Gemini and Anthropic public-boundary runs pass |
| restart and dogfood | not run | not run | not run | not run; prior acceptance diagnostics retained |
| overall | not run | not run | not run | partial |

Credential paths, access controls, binary startup, callback binding, and child
process launch are platform-shaped. No supported operating system is
**Not-Needed** for final acceptance.

## What this runbook cannot prove

The written open cells do not yet prove the corrected ChatGPT raw callback redirect-status
capture or the protected valid-key retry; native Linux, macOS or Windows
installed-product sessions; 31 credential-storage cells; 22 engine cells;
11 surface branch cells; a kill inside the owner dogfood batch;
or a monetary cost for ChatGPT OAuth usage. Those cells remain open and prevent
this runbook from declaring the minor fully accepted.

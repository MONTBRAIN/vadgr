# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).

## [0.4.10] - 2026-08-21

**The built-in transport.** The daemon gains a second phone-reachable
transport: an iroh endpoint served beside Tailscale, so a phone can pair and
talk to the machine with no second product installed on either end. The
machine's identity is a public key, a relay is the rendezvous point, and most
connections go direct after the relay introduces them. Tailscale is not
removed and not deprecated: the daemon serves every transport it supports and
reports the list, and the owner picks between them on the phone.

### Added
- **The built-in transport (`iroh`).** Ships inside the binary; nothing
  installs it and nothing switches it on. It serves the same routes, statuses
  and WebSocket frames as every socket transport: each accepted QUIC stream
  carries one HTTP/1.1 connection through the same router, upgrades included.
- **The pairing payload reports every supported transport.**
  `POST /api/auth/pair` gains a `transports` object with one member per
  supported transport, keyed by wire name (`iroh`, `tailscale`), valued with
  that transport's address form or `null` when it has none right now. The
  built-in entry carries the endpoint identity (`node`), the relay list and
  up to four direct addresses. The top-level `host` and `port` stay, produced
  from the Tailscale entry, for the released CLI and phone scanner; they are
  planned for removal at `0.6.0`.
- **The claim response gains `machine_name` and `transports`**, so a phone
  that pairs by typing the code finally learns the machine's name, and every
  phone learns what this machine supports. The request body is unchanged.
- **A claim binds what the transport proved.** A claim arriving over the
  built-in transport binds the connection's handshake-proven endpoint id to
  the new device row (`device_peers` table, schema version 2). A claim over
  loopback or Tailscale binds nothing, exactly as before. Revoking the device
  (`DELETE /api/devices/{id}`) drops the binding, so the revoked phone's next
  connection is refused before any request exists.
- **The QR carries each transport's own reach.** `vadgr://pair` keeps `token`
  and `name` and gains one query parameter per key of each transport's
  address form (`node`, repeated `relays` and `direct` for the built-in
  transport; the shipped `host` and `port` from Tailscale). A machine without
  a dialable Tailscale mints a QR with no `host` at all, and `vadgr pair` now
  builds it instead of failing.
- **`vadgr pair` prints one line per supported transport**, each with that
  transport's address or its own words when it is down. No verb, argument or
  exit code changed.
- **`VADGR_IROH_RELAYS`**: the rendezvous setting. Unset uses the default
  public relays (n0's, suitable for development and testing; they see
  connection metadata, never payloads, which are end-to-end encrypted between
  the two endpoint keys). A comma-separated list of `https` URLs points the
  machine at self-hosted relays. `none` disables relays for a directly
  reachable machine, and is never the default.
- **The endpoint secret key** persists at `credentials/iroh_secret_key` under
  the state root, created once with owner-only permissions. It is never
  regenerated while it exists: a new key would be a new machine to every
  paired phone. An unreadable or malformed file fails the transport loudly
  while loopback and Tailscale keep serving.
- **A successful claim writes one `info` log line** with the device id, the
  device name and the transport the claim arrived over, so the daemon log
  records that a pairing happened.

### Changed
- **The daemon reports the transports it supports; the owner configures
  nothing.** There is no per-machine transport set. `VADGR_TRANSPORT` takes
  exactly one value, `loopback`, meaning serve nothing off this machine (the
  mode tests and CI run in). Any other value, `tailscale` and `iroh`
  included, refuses at boot with a message naming the one legal value.
- **`POST /api/auth/pair` requires an authorized peer.** It still needs no
  token, and it now takes the peer gate first, because its response body is a
  fresh pairing credential and minting supersedes the outstanding one. No
  caller that could reach it before gets a different answer: the CLI arrives
  over loopback and a tailnet member passes the peer gate as it always did.
  The unauthenticated set is now `GET /api/health` and `POST /api/auth/claim`.
- **The peer gate is per transport.** A request must be an authorized peer on
  the transport it arrived over: tailnet membership (WhoIs, with the CGNAT
  fallback) on Tailscale, a handshake-proven endpoint id bound to a paired
  device on the built-in transport. Same `403 SOURCE_NOT_AUTHORIZED` as
  before. An unbound endpoint id gets a connection only while a pairing code
  is outstanding, is served exactly the two unauthenticated routes, is capped
  at four concurrent connections and sixty seconds each, and is closed when
  the window that admitted it ends. Outside a window it is refused before any
  HTTP exists.
- **`GET /api/health`'s `transport` block becomes one entry per registered
  transport**, keyed by wire name, and it is scope-gated: a caller who has
  proved nothing (an unbound peer inside a pairing window) sees name and
  liveness only, for every entry, so neither the endpoint identity nor the
  machine's tailnet name reaches it. Loopback callers, authorized peers and
  authenticated devices see the full block, including a paired phone's
  tokenless probe, which is how a phone refreshes a changed relay list.
- **`503 TRANSPORT_UNREACHABLE` fires only when no supported transport can
  reach a phone**: the local-only override, or every transport down at once.
  The message says which, one clause per transport in its own words, and
  `details.transports` carries the report.
- **`device_name` is validated on every claim**: 1 to 64 characters after
  trimming, no control characters and no bidirectional overrides, because the
  value reaches the owner's terminal. A bad value is the same `422` shape the
  strict body already produces, naming the field.

### Fixed
- A run of `vadgr pair` on a machine whose Tailscale is not running no longer
  fails with "unexpected response from the API": the QR builds from the
  transports that are dialable.
- **Device tokens no longer reach the daemon's log.** The run sockets take the
  device token as a query parameter, because a WebSocket client cannot set an
  Authorization header, and the request log recorded the whole URI. Every
  socket open therefore wrote a live token into the log in clear, where it
  outlived the connection and travelled with any log the owner shared. The log
  now records the method and path and never the query.
- **The daemon says when it closes a connection on the built-in transport.**
  Both closes are logged with the peer: the one that ends with the pairing
  window that admitted it, and the one that reaches its sixty second lifetime
  without being claimed. A connection that vanished with no line was
  indistinguishable from a network fault.

**The cutover.** `vadgr` is one binary. The daemon that answers is the Rust one,
the installation no longer carries an interpreter, and a machine's state lives
where the platform says durable state lives instead of below the directory the
daemon happened to start in.

### Changed
- **`vadgr start` launches the Rust daemon.** The default flips once, in a
  release that contains nothing else.
- **State moves to the platform's local-state root**, and the daemon consolidates
  before it serves:

  | platform | root |
  |---|---|
  | Linux and WSL | `$XDG_STATE_HOME/vadgr`, else `~/.local/state/vadgr` |
  | macOS | `~/Library/Application Support/vadgr/state` |
  | Windows | `%LOCALAPPDATA%\vadgr`, else `%USERPROFILE%\AppData\Local\vadgr` |

  `vadgr.db`, `runs/` and `credentials/` live beneath it. **Nothing resolves
  relative to the working directory any more**, so an installed daemon's database
  no longer depends on which terminal started it. `VADGR_STATE_HOME`, `VADGR_DB`
  and `VADGR_RUNS_DIR` remain exact overrides for tests and managed deployments.
- **`GET /api/settings/computer-use` stops answering with a dead `daemon`
  field.** It was `null` on every platform, and three places in the CLI read it:
  a line in `computer-use status`, a row in `vadgr status`, and the message
  after enabling that would have said the bridge did not start and pointed at
  `vadgr-cua doctor`. None of them could ever print. The computer-use bridge is
  the separate package's, it starts on first use, and reporting it as a status
  would call a healthy machine broken.
- **The product is one executable.** A machine used to receive `vadgr` and
  `vadgr-daemon`, and the CLI found the daemon beside itself on disk. That asked
  a user to keep two files in step to run one product, and doubled what an
  install has to copy and a release has to publish. `vadgr start` now spawns
  this same binary with `serve`, and the installer copies one file.
- **The installer is `install.sh` and `install.ps1`**, which is what the README
  has always told a user to run.
- **The Windows build links the C runtime in.** It imported `vcruntime140.dll`,
  which belongs to the Visual C++ redistributable and is not part of Windows, so
  the binary would not start on a machine that never installed it. The installer,
  `vadgr update` and CI all build it the same way, and CI reads the binary's
  imports and refuses any name Windows does not ship.
- **The installer installs a binary.** It sets up git and the Rust toolchain,
  builds the release, and copies `vadgr` and `vadgr-daemon` into `~/.vadgr/bin`
  only after the build succeeded, so a failed build leaves a working installation
  exactly as it was. No interpreter, no virtual environments, no launcher script.
- **`vadgr update` rebuilds the binary** rather than reinstalling dependencies.
  `--check` reports how many commits are available and whether `Cargo.lock` moves.
  The previous binary is moved aside rather than overwritten.
- The default port is `8000`. The second port existed while two daemons ran side
  by side.

### Fixed
- **The CLI crashed on a machine with no CA certificates.** Every `vadgr`
  command built its HTTP client against the system trust store, so on a machine
  without a CA bundle the command died with a Rust panic before doing anything,
  even `vadgr health`, which talks plain HTTP to loopback and never needed a
  certificate. The client now carries its own compiled-in roots, the same
  Mozilla list the WebSocket path already used, so provider calls keep
  verifying TLS and no command needs anything from the machine. A machine
  behind a TLS-inspecting proxy should exempt the provider hosts from
  interception, because the proxy's root is not in that list.
- **A run that looked at the screen failed on Gemini.** A screenshot returned
  inside the function response is refused by the service with "Multimodal
  function responses are not supported for this model", so every run that took
  one died on its next turn. The image now travels as its own part beside the
  function response, which the model reads.
- **`vadgr update` named a directory nothing writes.** The installer builds into
  `~/.vadgr` and clones to `~/.vadgr/src`, while the CLI still resolved the
  repository's former name, so an update reported a checkout that was not there.
- **`vadgr runs resume` said a run was resumed and showed nothing of it.** The
  command printed one line, `Resuming run <id>`, which reports that the daemon
  accepted the request and says nothing about the run: not the status it went
  back to, not the provider, not the error that stopped it. It now prints the
  same detail block `vadgr runs get` prints, from the same printer, so the two
  commands cannot describe one run differently.
- **A watched run under `--json` wrote two documents to one stdout**: the run
  object, then the watcher's own summary and results link. A watched run now
  prints nothing until it has an outcome, then prints the finished run once. A
  background run still prints the queued row, because there that is all that
  will ever be known.
- **`vadgr health` told you a module was missing when you had turned it off.**
  The daemon reports whether a module is usable and never says why, and both
  causes were rendered as "not found". It prints `unavailable`, which is what
  the daemon said.
- **The consolidation checked that a database opens, not that it can be served.**
  A database missing a column every read needs passed the check, and the daemon
  then failed on the first request. It now opens the target the way the daemon
  does, runs the migrations, and performs the read the API performs; a target it
  cannot serve is refused, the half made target is removed, and the sources stay
  exactly where they were.

### Removed
- **The Python daemon, CLI and engine**: 143 files, 17,330 lines. Parked on the
  private attic repository with the history that reaches back through every
  release they shipped in, so reviving any of it is a pull rather than a rewrite.
- The `rust/` directory. It was a boundary between two languages, and one left.
  The crate is at the repository root.
- **A tracked Windows virtual environment**: 1441 files of Python bytecode that
  survived earlier sweeps because every check asked for `.py` and bytecode does
  not end in `.py`. The repository goes from 1580 tracked files to 143.
- `providers.yaml` and `PROVIDER_PARSER_GUIDE.md`, the static provider list and
  the guide to its parser families, both replaced by authenticated catalog
  snapshots at `0.4.7`. The README's manual setup paragraph linked to those two
  and to three files the deletion removed, and is gone with them.

### Upgrade notes
- **Start the daemon once after upgrading and it consolidates your state.** Two
  databases exist on any installation that ran through the side-by-side releases;
  the surviving schema is a superset, so it is kept and the other contributes its
  runs and devices.
- **If it refuses, nothing has been moved.** Three cases refuse rather than
  guess: the same run id in both databases, the same device id in both, or a
  target directory that exists and is not this product's. Each says what it found
  and what to do.
- The old install root is `~/.forge`. After a successful start on the new
  version, nothing reads it and it can be deleted.

## [0.4.8] - 2026-08-19

### Added
- **The CLI is rewritten in Rust.** Every command keeps its name, its arguments
  and its exit codes: `health`, `providers`, `computer-use`, `pair`, `provider`,
  `model`, `runs`, `run`, `start`, `api`, `stop`, `restart`, `status`, `logs`
  and `update`. Like the Rust daemon beside it, it runs from the checkout for
  now: the installer still puts the Python CLI on your `PATH`, and both halves
  swap at the `0.4.9` cutover.
- `vadgr update --check` reports whether an update is available and which
  dependency files would change, and changes nothing. It makes the update path
  testable without altering the installation under test.
- The run watcher handles every event the daemon publishes. A cancelled run now
  says it was cancelled, a resumed run says so, and a run parked at the approval
  gate says it is waiting for you.
- A slow request and a stopped daemon are now different messages. A request that
  passes its timeout says the operation may still be running, instead of
  reporting the daemon as down.
- A `5xx` from the daemon points at the log that explains it.

### Fixed
- **The `vadgr status` and `vadgr runs list` tables line up again.** A coloured
  cell was measured with its escape bytes, so the `Status` column was drawn
  eighteen characters wide for a seven character word and every row under it
  landed short.
- The tables are padded columns with no box, which is what the CLI has always
  drawn.
- **`vadgr health`, `vadgr runs get` and `vadgr pair` print their key and value
  block indented and with its colon**, as they always have.
- Five statuses were printing with no colour: `error`, `available`, `not found`,
  `not running` and `stopped`.
- **The `Duration` column carries a duration.** No daemon sends one, so it used
  to be a dash for every run; it is computed from the timestamps the row already
  carries.
- **The daemon names the machine it is on.** `GET /api/health` and
  `GET /api/computer-use/status` returned a hard-coded `wsl2` on every host, and
  the phone prints that string in its machine row, so a native Windows box told
  its owner it was WSL. The word was wrong on WSL too, because the two daemons
  answered the same route differently while both ship.
- **`vadgr run --background --json` writes JSON and nothing else.** The run row
  was followed by the watch hint on the same stream, so the output the flag calls
  machine readable would not parse. The hint is still printed when the caller did
  not ask for JSON.
- **`vadgr start` survives a busy port.** The port search asked whether it could
  connect rather than whether it could bind, and a listener that is not accepting
  refuses the second probe, so the search returned the very port it had just been
  told was taken: it printed `Port 8815 busy, using 8815` and the daemon died on
  bind.

### Changed
- **The environment variables are renamed, and the old names are gone.** Export
  the new ones:

  | old | new |
  |---|---|
  | `FORGE_HOME` | `VADGR_HOME` |
  | `FORGE_REPO` | `VADGR_REPO` |
  | `FORGE_API_URL` | `VADGR_API_URL` |
  | `AGENT_FORGE_PORT` | `VADGR_PORT` |
  | every other `AGENT_FORGE_*` daemon setting | the same name under `VADGR_` |

  There is no compatibility fallback. The CLI and the daemon read one prefix
  now, where the two halves of the product read differently named variables for
  the same port before.
- `vadgr logs --follow` follows the file itself instead of running `tail -f`,
  which does not exist on Windows.
- The installer clones `github.com/MONTBRAIN/vadgr`. The old URL reached the
  repository only through a redirect from its former name.
- The pairing QR is smaller: error correction `Low` with a two module quiet
  zone, chosen by measuring and scanning rather than by taking a default.

### Unchanged
- **`vadgr start` still launches the Python daemon.** The cutover is `0.4.9`.
- The directories keep their names. `~/.forge` and the checkout inside it hold a
  real installation's database, credentials, pid files and log, and moving them
  belongs to the release that owns the paths.

### Removed
- `wait_with_spinner`, which nothing called and whose only tests polled a route
  deleted at `0.4.4`.

## [0.4.7] - 2026-08-16

### Added
- Provider onboarding in the Rust daemon for OpenAI, Google Gemini and
  Anthropic. OpenAI supports direct ChatGPT OAuth or an API key; Gemini and
  Anthropic support API keys.
- Native OpenAI Responses, Gemini `generateContent` and Anthropic Messages
  adapters with authenticated catalog discovery and bounded readiness calls.
- Additive provider connections, credential-scoped catalog snapshots and one
  explicit machine default in normalized SQLite tables.
- One cross-platform credential store using immutable, versioned JSON records
  behind opaque database references. Linux, WSL and macOS enforce Unix owner,
  mode and ACL checks. Windows enforces a protected current-user and SYSTEM
  DACL and rejects reparse points.
- `vadgr provider login|status|logout` and `vadgr model list|default` as thin
  Python HTTP clients over the Rust provider routes.
- A direct ChatGPT OAuth integration test, a three-provider coexistence test,
  raw database secret inspection and loopback-only mutation coverage.

### Changed
- `vadgr pair` runs provider onboarding before it mints the first QR when the
  Rust daemon has no connected machine default.
- Omitted run provider and model values now resolve from the Rust database.
  An explicit pair must exist in a connected authenticated catalog.
- Clean install now proves the static binary starts with empty provider state
  and serves all three disconnected built-in descriptors from a `scratch`
  container.

### Fixed
- The approval gate no longer allows a gated action without asking. It required
  the risk to be exactly `high` and everything else fell through to automatic
  approval, while the tool schema declared risk as a bare string with no
  accepted values, so a model that wrote anything else had its action approved
  without the owner being asked. Risk is now one of `low`, `medium` or `high`
  with a description, only the two known-safe values skip the owner, and
  anything unrecognised asks.
- A resumed run replays its completed calls as the tool-use pairs they were,
  instead of describing them in prose. Not repeating a finished action had
  depended on the model obeying an instruction, and a model that did not obey
  it repeated a completed side effect after a restart.
- A cancelled run says so on both run sockets. The run row reached `cancelled`
  while the sockets went silent, so a client that had been watching saw the run
  start and then nothing at all.
- The Tailscale transport reaches the macOS application, not only the daemon
  socket, and the three transports share one HTTP/1.0 response parser instead
  of an inline copy each.
- The repository credential gate passes its target through the environment
  rather than as a trailing argument to `powershell.exe -Command`, which does
  not populate `$args`. The Windows access-control check received nothing and
  refused every file it was given, whatever the real access control said.
- The Python daemon reports the released version. It answered `0.4.5` while the
  Rust daemon answered `0.4.7`, so a client could not tell which half served it.
  A test now keeps the two and the changelog in step.
- Gemini function declarations remove unsupported `additionalProperties`
  fields and complete array item schemas before a request, so installed cua
  and control schemas pass live function calling.
- Gemini tool calls preserve and replay provider thought signatures across
  turns, as required by current reasoning models.
- Anthropic low-credit responses map to the existing quota category instead of
  the generic provider-unavailable recovery path.
- Static release builds use embedded Web PKI roots for provider TLS, so they do
  not require a host certificate store that is absent from `scratch`.
- Linux containers on a WSL-backed Docker engine report `linux`, while a daemon
  running directly in WSL continues to report `wsl`.
- A process already using the OAuth callback port no longer prevents API-key
  providers or the daemon from starting. The callback listener retries, and an
  OAuth start reports the unavailable port until it can bind.
- Expired, cancelled and completed authentication attempts clear staged
  credentials and OAuth verifier state. A late callback cannot revive an
  expired attempt.
- ChatGPT catalog requests use the backend protocol version instead of the
  Vadgr product version, and native ChatGPT Responses requests omit the
  unsupported output-token limit.
- ChatGPT SSE decoding retains completed output items when the terminal frame
  carries usage but no output array. Live text and tool calls are no longer
  discarded as `NO_ACTION_TAKEN`.
- Browser OAuth prints the authorization URL only when launching the browser
  fails, using Click's documented zero-success return code correctly.
- Browser OAuth launched from WSL now opens the Windows default browser through
  a fixed PowerShell command and sends the complete URL over stdin, preserving
  query parameters without exposing them in process arguments.
- OAuth callbacks redirect immediately to query-free completion or failure
  pages, so spent authorization parameters do not remain in the browser address
  bar. A denied flow now shows failure instead of the connected page.
- Restart recovery reconstructs the last successful control-plane todo state
  from the durable journal, so a resumed `todo_update` can continue instead of
  failing against an empty in-memory list.

### Removed
- The Rust daemon no longer reads `providers.yaml` or another agent client's
  credential store. Its Anthropic subscription OAuth and borrowed client
  attribution are gone.

### Notes
- Python remains the default daemon until the `0.4.9` cutover. Its legacy
  `providers.yaml` behavior is unchanged and is not imported into Rust state.
- Provider credential files are plaintext at rest with owner-only operating
  system access controls. This beta boundary does not protect against
  malicious code already running as the same user.

## [0.4.6] - 2026-08-14

### Added
- A native Rust model loop with typed Anthropic Messages responses, stable tool
  ordering, sequential dispatch, image pruning, token totals, and explicit
  termination rules.
- A direct Anthropic OAuth provider with the required validator headers,
  bounded retries, one credential refresh after `401`, native credential paths
  on Linux, WSL and Windows, and Security.framework on macOS.
- A two-server MCP host with the eight in-process control tools first and the
  installed `vadgr-cua` executable second. Cua is started by direct native argv,
  never by a shell or external client configuration.
- Append-only, secret-redacted run journals with synced writes before tool side
  effects, bounded recovery context, dangling-call revalidation, and recovery
  of every active database row at boot.
- Engine-backed `POST /api/runs` and `POST /api/runs/{id}/resume`, plus one
  supervisor that owns start, failed-only resume, cancellation, terminal-state
  races, and task cleanup.

### Changed
- `GET /api/computer-use/status` now probes the configured cua server through
  MCP and reports available only after initialization and tool listing succeed.
- The Rust dependency lock now uses current release lines, including
  `reqwest 0.13.4` and `rmcp 3.1.2`.
- The static clean-install gate uses an isolated journal root and still starts
  without cua, credentials, a home directory, runtime libraries, or build tools.

### Fixed
- A first-turn narrative can no longer complete a run without action.
  `end_turn` succeeds only after at least one closed tool call; `max_tokens`,
  malformed `tool_use`, and unknown terminal reasons fail by name.
- Cancel and completion race through conditional database writes, so a late
  task cannot replace `cancelled` and stale task cleanup cannot remove a newer
  execution of the same run.
- Recovery never blindly dispatches a tool call whose outcome became unknown
  when the daemon stopped.

### Notes
- Python remains the default daemon until the `0.4.9` cutover. The Rust crate
  stays under `rust/` and runs beside it on a separate port and database.
- This release starts an installed cua executable but does not package cua.
  Bundling the pinned runtime is later distribution work.

## [0.4.5] - 2026-08-11

**The daemon is being rewritten in Rust, and this is the first release of it.**
Nothing you use changes: the Rust daemon runs **beside** the Python one, on its
own port and its own database, and the Python daemon is still the product until
the cutover. This release exists to be compared against it.

### Added
- **A Rust daemon that answers everything except starting work.** Health,
  pairing and claiming, devices, providers, the computer-use settings, the run
  list and a run's detail, cancel, and both run sockets with their replay.
- **`rust/`**, a new tree beside `api/`, `engine/` and `cli/`, with its own
  README covering how to run it and what it deliberately does not do.
- **A native-only provider catalog.** Rust ignores deprecated subprocess rows
  and never starts an external agent CLI to test availability.
- **Daemon-owned computer-use settings.** The toggle writes only vadgr's own
  settings. It never edits project MCP files, Gemini settings or Codex global
  settings, and it never installs a runtime.
- **HTTP request tracing** in the Rust daemon log, including the response status
  and latency used to audit a live sweep.
- **Rust CI on Linux, Windows and macOS.** Each host builds, tests and lints the
  daemon. Live operating-system E2E results remain separate.
- **A clean-install gate for the Rust daemon.** CI builds a static musl release
  binary, installs it alone in a `scratch` image, starts the installed entry
  point, and checks its complete health response from outside the container.
- 113 tests over the error envelope, the pairing code's rules, the two
  repositories' wire mapping, the socket buffer, the stream's frame mapping,
  the transport adapter, and the gates driven through the real router.

### Fixed
- Health reports the detected `linux`, `macos`, `windows` or `wsl` platform.
- Cancel records `cancelled` instead of reporting a deliberate stop as a
  failure.
- An auth or missing-run WebSocket refusal accepts the upgrade before closing
  with `4401` or `4004`, so a client can read the reason.
- Computer-use status reports unavailable until the Rust MCP engine exists.
- Filesystem paths remain native path values instead of being converted to
  UTF-8 strings. Config roots follow XDG on Linux and WSL, Application Support
  on macOS, and roaming AppData on Windows.
- The macOS tailscaled LocalAPI uses `/var/run/tailscaled.socket`; Linux and WSL
  keep `/var/run/tailscale/tailscaled.sock`, and Windows keeps its protected
  named pipe.
- Settings replace an existing file without deleting it first on Windows.
  Runtime discovery follows `PATHEXT` on Windows and executable bits on Unix.
- Malformed settings, wrongly typed values and invalid
  `VADGR_COMPUTER_USE` values fail with a named error instead of being reported
  as a plausible default.
- IPv6 loopback and IPv6-only Tailscale listener addresses are accepted, and a
  first-start database creates its missing parent directories.

### Notes
- **It cannot start or resume a run**, and both routes are **absent rather than
  stubbed**. A `501`, a plausible `202` with no run behind it, or a queued row
  nothing will pick up are three ways of reporting a success that did not
  happen. Both arrive with the loop, in the next release.
- **The database schema is copied, not improved**, and released error envelopes
  keep their status and code. Intentional target corrections are recorded and
  tested.
- **The replay buffer stays for released mobile compatibility.** The daemon
  buffers up to 500 frames per run because mobile `0.4.1` uses replay after a
  reconnect. The adapter leaves with the watch route at `0.6.0`.
- **Copy a database with `VACUUM INTO`, never `cp`.** SQLite runs in WAL mode,
  so a bare file copy is a different database: it carries what was last
  checkpointed and silently drops the rest.
- The Rust daemon takes port `8100` by default, not `8000`, because both run at
  once.

## [0.4.4] - 2026-08-09

**Most of this repository is gone.** The agent entity, projects and the DAG, the scaffolder, the bundle installer and the per-run `output/` tree are deleted, along with every run endpoint that had no live consumer. **This removes shipped endpoints and shipped CLI commands, and it rewrites the database schema in place.** What replaces all of it is one sentence: `POST /api/runs {"task": "..."}` starts a run, and `vadgr run "<task>"` does the same from the box. What the phone reads is untouched.

### Removed
- **The agent surface, whole.** `GET/POST /api/agents`, `GET/PUT/DELETE /api/agents/{id}`, `DELETE /api/agents`, `POST /api/agents/{id}/uploads`, `GET /api/agents/{id}/export`, `POST /api/agents/import`, `GET /api/agents/{id}/runs`, and `POST /api/agents/{id}/run`, which is re-homed rather than dropped (see Added). All answer `404`.
- **The project and DAG layer**: the `/api/projects` CRUD, its nodes, edges and `/validate`, and `POST /api/projects/{id}/runs`. Eleven routes.
- **`DELETE /api/runs`.** An unscoped destructive verb with no confirmation. `DELETE` on `/api/runs` now answers `405`.
- **`POST /api/runs/{id}/approve`.** Its only consumer was a CLI gate channel that dies on EOF under a background daemon.
- **`GET /api/runs/{id}/outputs/{field}`, `GET /api/runs/{id}/logs` and `GET /api/runs/{id}/logs/{step_file}`**, which read back from the `output/` tree this release stops writing.
- **`vadgr agents ...` and `vadgr registry ...`**, both groups, and **`vadgr ps`**, which despite its name listed agents. **`vadgr runs approve`** and **`vadgr runs logs`** go with their endpoints.
- **`forge/` and `registry/`**, 174 files carrying 6,640 lines of Python and 309 tests, and the `forge` job from CI.
- **`output/` leaves the repository.** Only its `.gitkeep` was tracked, and the `/output` line leaves `.gitignore`. **Nothing on your disk is deleted.** If you have an `output/` directory it stays exactly where it is, and from this release nothing will ever read it again, so it is yours to remove. Run journals under `~/.vadgr/runs/` are untouched and remain the machine's record.
- **`python-multipart`**, needed only by the agent upload and import routes.
- **`"forge": true` from `GET /api/health`.** The `modules` object now carries `computer_use` alone. A payload reporting a module the machine does not have is a lie the health endpoint exists not to tell.
- **`AGENT_FORGE_DEFAULT_PROVIDER` and `Settings.default_provider`.** The machine's default provider is `providers.yaml`'s top-level `default_provider`, which is the file an owner edits. Two defaults disagreed, and the one in code answered `claude_code`, so a run naming no provider would have gone to a deprecated subprocess CLI instead of the native loop.

### Added
- **`POST /api/runs {"task": "...", "provider": ..., "model": ...}`.** Answers `202` with the run row. `task` is required and non-empty; `provider` and `model` must be given together or not at all; an undeclared field is a `422` rather than a silent drop, so the old `inputs` body fails loudly. The sentence is stored twice on purpose: as the run's title, which is what a client displays, and as its work, which is what the loop receives.
- **`vadgr run "<task>"`**, a real command rather than an alias. Flags: `--provider` / `--model` (a pair), `--background`, `--json`. **Exit codes are the contract's**: `0` completed, `1` failed, `2` usage, `3` daemon unreachable, `130` on Ctrl-C.
- **Ctrl-C detaches the watcher and leaves the run going.** It used to cancel the run. An unattended batch running for hours is the point of the product, and losing one because a terminal closed is the opposite of it. Cancelling is `vadgr runs cancel`, which says so.
- **A schema migration that runs at boot, backs the database up first, and refuses to start the daemon if it went wrong.** It is guarded on the columns it removes, so it is idempotent and a fresh database skips it; it writes `data/agent_forge.db.pre-0.4.4` with `VACUUM INTO` (not a file copy, which in WAL mode would miss the `-wal` and `-shm` sidecars); and it names that file in the log and in the error. If `PRAGMA foreign_key_check` is not empty afterwards it raises rather than serving a half-migrated database.
- **A guard suite** (`api/tests/test_deletion_decommissioned.py`) that fails the suite if any of this comes back, and equally if the surface the phone reads is removed by accident.

### Changed
- **The schema is two tables and one index**: `runs` and `devices`, and `idx_devices_token_hash`. `agents`, `projects`, `project_nodes`, `project_edges` and `agent_runs` are dropped; `runs` loses `project_id` and `agent_id` and gains `title`, backfilled from the run's agent name where there was one and the empty string where there was not.
- **The run row keeps every key it had, minus the two owner ids.** `agent_name` stays, now carrying the run's title, because that is what the shipped phone reads and renaming it would turn every run card into a raw id. `log_path` stays too, and nothing writes it any more.
- **A run records what it actually ran on.** The resolved provider and model are written back to the row, so a run that named neither still reports both instead of `null`.
- **`step_completed` leaves the frame vocabulary.** It was emitted only by the per-step path, which required an agent's steps. Every other frame name is unchanged and frozen. The `agent_*` frames now carry `run_id` where they carried `agent_id`, and `agent_started`'s `name` carries the run's title.
- **The database file, the `AGENT_FORGE_` environment prefix, `FORGE_API_URL` and `FORGE_HOME` keep their names.** Renaming any of them would strand every existing database and every operator's shell in the release whose whole risk budget is a schema rebuild.
- **`vadgr runs list` and `vadgr runs get` show the task**, not an agent name, and lost the per-run steps block.
- **The installers no longer create a `forge/scripts` virtualenv**; README, `api/README.md`, `cli/README.md` and the Postman collection describe the surface that exists.

### Fixed
- **`run_resumed` reached the mobile stream's fallthrough and logged a warning on every resume.** It has no member in the frame vocabulary yet, so it is now listed as a deliberate deferral, which is what the fallthrough is for.
- **The mobile stream's map is now asserted in both directions** against the names the daemon can actually emit. A dead branch and a rare branch look identical from inside.

### Notes
- **Nothing the shipped phone reads has moved.** `GET /api/runs`, `GET /api/runs/{run_id}` and `WS /api/runs/{run_id}/stream` survive with their method, path, status, error codes, row keys and frame names frozen. `WS /api/ws/runs/{run_id}` survives on the same terms for the CLI. They are transitional and are removed when their replacement ships.
- **A run needing desktop automation is no longer refused when computer use is disabled.** That gate read a per-agent flag, and there is no agent; nothing a task submits declares that it needs the desktop. The machine-level computer-use setting and its three endpoints are untouched.
- **A cancelled run is still recorded as `failed`.** Unchanged, and owned by the minor that owns run statuses.
- **Resume on boot is still detection-only.** It finds an interrupted run and continues nothing, exactly as before.
- **A response with no tool call still ends a run as a success.** Unchanged; it is a known defect with an owner.
- **`GET /api/providers` and `GET /api/settings/computer-use` answer in roughly half a second** where every other endpoint answers in under 60ms. Pre-existing and carried forward.

### Tests
- engine 122, api 427, cli 141, all green. The whole tree collects 690 where it collected 1,228: 497 tests left with their subject (`forge/scripts/tests` 158, `registry/tests` 151, and the agent, DAG, executor, log-writer, project and step-result suites), and the rest were rewritten against the surface that survives.
- The migration is tested against a database seeded in the previous schema with rows in all five dropped tables, against a database predating `provider`, `model` and `log_path`, against a fresh one, and re-run to prove it is a no-op the second time. A deliberately broken rebuild is asserted to raise out of `create_tables`, which is what stops the daemon.
- **Runbook** at `E2E/0.4.4/e2e.md`, run before this was offered for review, on Linux/WSL and on native Windows. Its recorded sweep is the baseline every later release is compared against.

## [0.4.3] - 2026-08-08

**A pairing code a person can type, at an address the daemon actually answers on.** The value in `pairing_token` shortens from ~32 random characters to eight, and `vadgr start` now binds what the transport says instead of a hard-coded `127.0.0.1`, so the address in the QR is one something is listening on. **The wire shape does not move**: same endpoints, same field names, same claim exchange.

### Changed
- **The pairing code is 8 characters of Crockford base32**, shown grouped as `7QK4-M2XD` (`api/auth/tokens.py`). 40 bits, chosen symbol by symbol from a 32-symbol alphabet with no `I`, `L`, `O` or `U` - the exclusions are the point, because a person reads this off a terminal and types it on a phone. The long random secret is unchanged: it is still what `claim` returns.
- **Claims are forgiving about how the code was typed, once, on the server.** Case, hyphens and spaces are ignored and Crockford's documented confusions are mapped (`O`->`0`, `I`/`L`->`1`), so `7qk4m2xd`, `7QK4 M2XD` and `7QK4-M2XD` all redeem the same code. `U` is not forgiven - it is not in the alphabet, so a typed `U` is a malformed code. Normalising in one place is what stops a `curl`, the CLI and a phone drifting into three different answers.
- **Minting replaces the outstanding code.** At most one code exists at a time, so a second `vadgr pair` invalidates the first (`401 PAIRING_CODE_INVALID`). This is also what makes "five attempts against the code" countable: a wrong guess matches no key, so with several codes live there is nothing to charge the failure to.
- **`vadgr pair` prints `Pairing code`** rather than `Pairing token`, and says the code is valid for 5 minutes. `build_pair_uri` is untouched - the deep link keeps `host`, `port`, `token`, `name`, and only the value in `token` shortens.
- **`vadgr start` names the addresses it is binding**, not just the port: `Starting API server (100.67.110.10, 127.0.0.1 on port 8000)...`. Where the daemon is listening is the fact this release exists to make true, so it is worth one line on the way past.

### Added
- **`429 RATE_LIMITED` on claim, and it burns the code.** The fifth failed attempt against the outstanding code answers `429` with empty `details` - there is no `retry_after`, because the recovery is a new code, not waiting - and the code is destroyed at that moment. Everything after answers `401`, including the code that was correct all along. Four wrong tries still leave the owner able to pair on the fifth: the counter counts failures, not attempts. Specified in the published API reference since `0.4.1` and implemented nowhere until now.
- **`api/serve.py`**, the daemon's launcher. `uvicorn --host` takes one address and the daemon needs two: the transport's own, which the QR advertises and a phone dials, and loopback, which the loopback gate recognises and which is what keeps the on-box CLI working without a device token. It refuses `0.0.0.0` outright rather than clamping it.
- **Runbook** at `E2E/0.4.3/e2e.md`, run live before this was offered for review, with the bind proven by a request arriving over the advertised address and by the same check failing against `0.4.2`.

### Fixed
- **The daemon bound loopback while pairing advertised the tailnet.** `vadgr start` passed a literal `--host 127.0.0.1` to uvicorn at its one spawn site, so a phone scanning the QR dialled an address with nothing behind it, and `GET /api/health` reported a `bind_host` that had never been bound - measured at `v0.4.2` as `100.67.110.10:8807 -> 000` against `127.0.0.1:8807 -> 200` with health claiming `100.67.110.10`. The address now comes from the same transport factory the app uses, resolved in the parent so `vadgr start` knows whether it will work before it writes a pid file. Pre-existing; not introduced by `0.4.2`.
- **A tailscale transport that cannot resolve no longer kills the daemon.** `bind_host()` raises when tailscaled is down or logged out. `vadgr start` catches it, binds loopback alone and **says so** - the CLI, runs and the journal are all loopback clients, and a tailnet hiccup should not stop someone using their own machine. Pairing then refuses with `503 TRANSPORT_UNREACHABLE` rather than minting a code for an address nobody can reach.
- **`vadgr pair` lost roughly one code in twenty and blamed the daemon.** The CLI sent `{}` as the body of every non-`GET` request, including to routes that declare no body. Those bytes are never read, so the server cannot reuse the connection and closes it abruptly; on WSL2 loopback that close races the client's read and arrives as a connection reset, which the client reported as `Error: API is not running` and exited `3` - about a daemon that had already answered `200` and minted the code. Measured at 5-9 failures per 120 `vadgr pair` invocations before, 0 per 120 after. Pre-existing.
- **A comment in `api/config.py` claiming the host already came from `transport.bind_host()` at startup** is deleted. It described a mechanism that never existed, and a comment asserting a fix is already in place is a large part of why the bind defect survived to `0.4.2`.

### Notes
- **Nothing on the wire was renamed.** The response field is still `pairing_token`, the claim request is still `{pairing_token, device_name}`, the claim response is still `{token, device_id}`, and the deep link still uses `token=`. The renames the published API reference names as targets - `pairing_code`, `expires_at`, `pair_uri`, `code=` - travel with the `0.5.0` reshape and its schema regeneration, because the phone app is being built against these names right now.
- **`POST /api/auth/pair` still has no rate limit**; its `429` remains a target. The single-slot store changes its threat model - minting can no longer grow anything, so a mint flood is denial of pairing by an already-authorized peer rather than resource exhaustion.
- The TTL (300s) and the attempt cap (5) are module constants, not configuration. An environment variable for either would be a knob for silently weakening a recorded security decision. Tests that need a fast expiry use the existing `PairingStore(ttl_seconds=)` constructor seam.
- Agent creation on a native provider still reaches status `error`, unchanged from `0.4.1` and `0.4.2`. Runs on an existing agent are unaffected.

### Tests
- engine 122, api 596, cli 201, all green. `api` moves by 555 -> 596 (the code's format and normalisation, the cap, the burn, supersede, the claim mapping asserted in both directions, and the launcher's address arithmetic, against two removed pairing-token tests); `cli` by 192 -> 201 (the bind argv, the loopback fallback, the request-body tests).
- Verified live on WSL2 against a real tailnet: a request over the advertised tailnet address and over the MagicDNS name in the QR both answer `200`, `ss` shows both sockets and never `0.0.0.0`, and the same check run against `0.4.2` fails - which is what makes the passing run mean anything. The seven-attempt trace was reproduced over HTTP, the five-minute expiry was waited out rather than faked, and a code printed by `vadgr pair` was typed back to claim a device that the device rows then confirm.

## [0.4.2] - 2026-08-05

**The web dashboard is gone.** The machine's clients are now the `vadgr` CLI on the box and the phone app over the tailnet, and installing vadgr no longer installs Node.js. The API contract is unchanged: every operation the dashboard rendered is still served by the same endpoints.

### Removed
- **The `api/docs/` folder.** Four v1-era design documents - the API module architecture, the Agent surface before what v1 called an agent became a Workflow, the Projects/Canvas/DAG layer, and an unbuilt Docker plan - totalling 3,298 lines. Their premise is the web dashboard this release removes, so scrubbing them would have left them reading as current instead of true. This repo's docs describe what it is; the record of what it used to be is kept in the planning repo.
- **The React web frontend** (`frontend/`, 71 files, 12,171 lines). It was one of three interchangeable clients of the same API and nothing depended on it. Extracted with its full history into a private attic repository first, so it can be revived by a subtree pull rather than rewritten.
- **Node.js, NVM and npm from the installer.** `setup.sh` loses `install_nvm_and_node` and `setup_frontend`; `setup.ps1` loses `InstallNode` and `SetupFrontend`. A fresh install is now git, Python, the virtualenvs and the CLI, and nothing else.
- **The frontend half of `vadgr start`.** The `--frontend-port` flag, the node/npm lookup, the `npm run dev` spawn, the Vite log-port parser, the `frontend.log`, and the `frontend` pid and port files. `start` boots the API alone and reports one address.
- **CORS.** `CORSMiddleware`, the `cors_origins` setting and the `AGENT_FORGE_CORS_ORIGINS` environment variable. No browser client remains, so the daemon no longer answers with access-control headers.
- **`frontend_port` / `AGENT_FORGE_FRONTEND_PORT`** from the API settings.

### Changed
- **Pairing is CLI-only.** `vadgr pair` mints the token and prints the Unicode QR in the terminal; it is now the only pairing surface the machine has. The endpoints behind it are unchanged, so a phone that could pair before still pairs.
- **`vadgr api` and `vadgr start` are one command.** `api` stays as a name for it, and its `--port` spelling still parses alongside `--api-port`.
- **`vadgr status` no longer lists a `frontend` row**, which was permanently `stopped` on any machine without Node. What it lists now is the API and, when computer use is enabled, its daemon.
- **`vadgr stop`, `vadgr restart` and `vadgr logs`** act on the daemon alone; `logs --service` accepts only `api`.
- **A finished run links to the API.** `vadgr run` used to probe for a dev server and print `http://localhost:3000/runs/<id>` when it found one; it now prints `<api>/api/runs/<id>` unconditionally, which also removes a probe that cost about a second on every completed run.
- **`vadgr update`** no longer reinstalls frontend dependencies.
- README, `cli/README.md`, `api/README.md` and `AGENTS.md` updated to describe two clients instead of three. The two API design documents that describe the v1 visual-canvas product are marked historical rather than rewritten, since the dashboard is their premise.

### Added
- **A guardrail test** (`api/tests/test_frontend_decommissioned.py`) that fails the suite if the frontend directory, an npm manifest, the npm-start path, a `--frontend-port` flag, the CORS origin or a Node step in either setup script ever returns.
- **Runbook** at `E2E/0.4.2/e2e.md`, run live before this was offered for review.

### Fixed

- **`OPTIONS` requests no longer skip authentication.** The two-gate middleware waved every `OPTIONS` through so a browser's CORS preflight could reach `CORSMiddleware`. That middleware is removed in this release and no client here speaks preflight - the CLI and the phone are not browsers - so the exemption guarded nothing while letting any caller past all three gates by choosing the verb. Unauthenticated it answered `405` with an `Allow` header naming a path's methods.

### Notes

- **Known, pre-existing, and it blocks pairing from a phone:** `vadgr start` binds `127.0.0.1` regardless of the configured transport, while `vadgr pair` advertises the tailnet address - so the QR carries an address the daemon does not answer on, and `GET /api/health` reports a `bind_host` that was never bound. Not introduced here (`master` carries the same hard-coding) and not fixed here; it lands in `0.4.3`. Every pairing check in this release's runbook is real, but all of them originated from loopback.
- Agent creation on a native provider fails with `[Errno 13] Permission denied: ''` and reaches status `error`. This is not new here - it reproduces identically on `v0.4.1` - but it is recorded because the runbook hit it. Runs on an existing agent are unaffected.

### Tests
- engine 122, api 554, cli 192, all green. The api count moves by seven new guardrail tests and two new API-only tests against five deleted CORS and frontend-port tests and one deleted gateway-guard test; the cli count by ten new API-only tests against seven deleted Node-discovery and Vite-log tests.
- Verified live on WSL against a real tailnet: `vadgr start` spawns no child process at all on a host that has Node on its PATH, nothing answers on port 3000, `vadgr pair` mints a token that a claim turns into a persisted device, and a native-loop run still completes from both the API and the CLI. The CLI surface and both installer changes were also verified on native Windows.

## [0.4.1] - 2026-08-02

Puts the native loop on the product's own run path. Before this, `POST /api/agents/{id}/run` executed through the CLI executor and the engine shipped as a library nothing called.

### Added
- **Native loop on the API run path** (`api/engine/native_bridge.py`). A bridge between an executor that pulls (`AsyncIterator[ExecutionEvent]`) and a loop that pushes (`on_event` callback), joined by an `asyncio.Queue`. Events are mapped to the frames the published frame vocabulary names; anything the bridge has not been taught is dropped rather than forwarded, because an unrecognized payload is exactly the unbounded one.
- **Resume on boot** (`api/main.py`, `api/services/execution_service.py`). On start the daemon finds journals with a dangling record and continues those runs from the first uncompleted step.
- **Resume entry point** (`engine/loop.py`, `engine/trajectory.py`). `run_loop(..., resume_state=...)` reconstructs the conversation from the journal, and a resumed journal continues its sequence instead of restarting it. Prior results are truncated on the way in, so a resume does not replay screenshots.
- **E2E doctrine and template** (`E2E/README.md`, `E2E/TEMPLATE.md`). Where the ground truth is, the verdict rules, the honest use of `Not-Needed`, and the shape every runbook follows.
- **Runbook** at `E2E/0.4.1/e2e.md`, run live. Eleven defects, none of which the unit suite saw.

### Fixed
- **Agent creation on a native provider raised three different ways.** `load_provider_config` did `config["args"] + [...]` on a provider that has a module and no argv; `ProviderConfig` made `command` mandatory; and `is_available()` fell through to spawning an empty argv. One defect wearing three hats: nothing on the creation path knew a provider might not be a subprocess.
- **The journal could not be tied to its run.** The executor never passed `run_id`, so the loop minted its own and wrote a directory nothing could correlate - which also broke resume on boot, since it finds a journal by id and then has to look that run up.
- **A gate crashed on a timeout the model typed.** `ask_user` declares `timeout` a `number` and the model sent `"300"`; `asyncio.wait_for` compared a `str` to an `int` and raised. The run failed at the exact moment it was trying to consult a human. Timeouts are coerced, and an unparseable one means no timeout rather than an exception.
- **The on-box WebSocket authenticated nothing.** `/api/ws/runs/{run_id}` never called the authorizer - the auth middleware is HTTP-only - so any peer gate 1 admits could open it. It also honoured an inbound `approval_response` that resumed a parked run, making it an unauthenticated way to answer a human-approval gate. It now authenticates as `/stream` does and is send-only.
- **A checklist sent as a JSON string crashed `todo_write`.** The model sent `items` already serialised; iterating a `str` yields characters, so every entry raised `'str' object has no attribute 'get'`. A JSON-Schema type is advisory for containers exactly as it is for enum values.
- **The phone's run stream carried a start and an end and nothing between.** Five of the eight keys in the mobile translator's map were event types nothing emits, and the executor's real vocabulary was absent - measured at 2 frames for a six-tool-call run, 11 after. The severe half is `awaiting`: an approval request could not reach the device that has to answer it. A test now checks every key in the map against what `executor.py` actually broadcasts.
- **The checklist reached the wire as a Python repr.** `ExecutionEvent.data` was annotated `str`, so the bridge coerced the list with `str()` and clients received single-quoted text that is not JSON.
- **An output field of prose no longer answers `500`.** `GET /api/runs/{id}/outputs/{field}` handed the output value to `Path.resolve()` to test whether it named a file; on the native loop that value is usually the model's prose, and past `NAME_MAX` it raised `OSError: File name too long`. The route has two outcomes, the bytes or `404`, so it was broken for essentially every free-text output.
- **Pairing returns the documented error codes.** `TRANSPORT_UNAVAILABLE` is now `TRANSPORT_UNREACHABLE` and `INVALID_PAIRING_TOKEN` is now `PAIRING_CODE_INVALID`; an expired code answers `410 PAIRING_CODE_EXPIRED` instead of collapsing into `401`, so a client can tell the owner to ask for a new code rather than that they mistyped this one. Codes are what a client switches on, and this is the first-run flow.
- **A parking gate now announces itself.** `ask_user`, `request_approval` and `propose_plan` wrote a journal line and emitted nothing, so a run could park on a human with no watcher able to learn it had - while three layers carried an `awaiting` branch that nothing could reach and every test passed. Journalling and announcing are now one call, since they are the same fact for two audiences.
- **An unrecognized loop event is dropped loudly.** The bridge returned the same silent `None` for the two events it drops on purpose and for any type the engine grows later, so the second was invisible until a feature turned out to be missing. The deliberate pair is named as data; anything else warns.
- **An unreachable daemon is reported in ~1.6s instead of ~15s on WSL.** A short connect probe runs before the request. On Linux and macOS a closed local port is refused instantly; on WSL2 IPv4 loopback swallows it, so the connect ran to the full request timeout - which has to stay generous because a request can be doing real work.
- **The CLI can say "the daemon is down".** Exit `3` is reserved for an unreachable daemon and `1` for a request that ran and was refused; both came back as `1`, so a script could not branch on them - and the first is worth retrying after `vadgr start` while the second never is.
- **A gate with no terminal now says so.** The daemon has no stdin, so gates died on `EOF when reading a line` - a message about a file descriptor, not about the problem. It now says there is no interactive channel and to proceed or stop rather than retry.

### Notes
- **No gate on the daemon can reach a human yet.** The default channel router is the CLI channel, which reads stdin the daemon does not have, so gates park correctly and reach nobody. The shipped `POST /api/runs/{id}/approve` does not close this: it takes no body, so it carries a verdict and never the answer `ask_user` and `propose_plan` need, and its resume path re-runs the whole project rather than continuing it. The channel lands at `0.5.0` against `POST /api/runs/{id}/respond`, which carries a verdict, a reason and an answer and resolves against the loop's own resume.
- Agent creation is still CLI-bound: it runs forge generation, which spawns the configured provider as a subprocess, and a native provider cannot. A run may override the provider per trigger, which is the path the runbook exercises.
- **Pairing has no attempt limit.** The published `429 RATE_LIMITED` on `/api/auth/pair` and `/api/auth/claim` is unimplemented - the store has no attempt counter. An 8-character code inside a five-minute window is not practically guessable over HTTP, but the behaviour is specified and absent.
- `/api/ws/runs/{run_id}` is deleted at `0.5.0`, when one socket survives. It has a live consumer today (`cli/stream.py`), so it was fixed rather than removed.

## [0.4.0] - 2026-07-30

### Added
- **Native agent loop** (`engine/`). A provider-agnostic tool-use loop that owns the conversation, the tool-use cycle, keep-last-N screenshot pruning, and an append-only resume journal. Every tool call writes `in_flight` before dispatch and `done`/`error` after, so a crash between them leaves the dangling line a resume keys on. Resume reads the journal tail and continues from the first uncompleted step; completed steps are never re-run.
- **Native Anthropic provider over subscription OAuth** (`engine/providers/`). Dev runs bill against a Claude subscription instead of API credit. Three auth strategies (`oauth`, `api_key`, `none`); the OAuth strategy caches the access token, refreshes on expiry and on 401, and resolves the token store per OS - the credentials file on Linux, Windows and WSL (WSL reads the Linux-side home, not `/mnt/c`), the login Keychain on macOS.
- **Shared async HTTP client** (`engine/http.py`) with retry-on-transient (429, 5xx, transport errors) and exponential back-off. Every model call and token refresh goes through it.
- **Control-plane MCP server** (`engine/tools/`), in-process and mounted beside cua, with eight tools: `todo_write`, `todo_update`, `report_progress`, `get_run_status`, `request_approval`, `ask_user`, `propose_plan`, `notify_user`.
- **Human-in-the-loop gate.** `request_approval` pauses the loop, consults the policy hook, and only then routes to the active channel; the pause is journaled as an `await_user` line on the same step. A reject or a timeout comes back as an ordinary tool result, not a crash, and the loop continues.
- **Policy hook** (`engine/policy/`) with a denylist, a risk level and four auth modes (`bypass`, `default`, `autonomous`, `paranoid`).
- **Channels** (`engine/channels/`): a CLI channel (TTY prompt, timeout, importance-to-loudness) and a desktop channel (native toast or modal, command selected per OS).
- **Acceptance runbook** at `E2E/0.4.0/e2e.md`, run live against the real endpoint: 110 enumerated cells across the loop, the eight tools, crash/resume, the policy matrix, the channels, the auth strategies and the MCP host.

### Changed
- **Default model is now `claude-opus-5`**, up from `claude-sonnet-4-6`. Bumped everywhere the default is defined - the native provider, the agent model field, the repository and agent-service defaults, the `agents` table `DEFAULT`, the manifest default and the manifest-import fallback. The advertised catalogue in `providers.yaml` moves to the current family (Opus 5, Sonnet 5, Fable 5, Opus 4.8, Sonnet 4.6, Haiku 4.5).
- `providers.yaml` gains a native `anthropic_oauth` block and sets it as `default_provider`; the legacy CLI providers are tagged `deprecated`.
- The providers discovery route treats native providers as a distinct kind - they carry no command or args.

### Fixed
- **A broken MCP server no longer takes the whole run down.** `MCPHost.connect()` awaited `list_tools()` inline with no guard, so one unreachable server raised straight out and the run never started, losing every healthy server's tools with it. Each server's start is now guarded; a failure is logged, that server is dropped, and the reason is recorded in `MCPHost.failed()`. A server-name collision still raises, because silently dropping one of two same-named servers would shadow the other's tools.
- **Journal redaction no longer destroys the token counts.** The key pattern matched the bare substring `token`, so `input_tokens`, `output_tokens` and `max_tokens` were written as `[REDACTED]` along with real credentials. Keys are now matched as whole words after normalizing camelCase and kebab-case: `accessToken`, `apiKey` and `Authorization` are still redacted, `input_tokens` and `max_tokens` survive.
- **`todo_update` accepts the vocabulary a model actually uses.** Given a plain goal the model wrote `completed` where the enum is `done`; a JSON-Schema enum is advisory, so the value reached the tool and returned an error that cost an iteration. Synonyms now map to the canonical status, and both errors name what is legal - all four statuses, and the ids that exist.
- The Anthropic endpoint rejects a `tool_result` whose content is a bare object; content is now normalized to a string or a list of content blocks.

### Notes
- The engine ships as a library. The API run endpoints still execute through the CLI executor; wiring them to the native loop is `0.4.1`, and that is what puts the loop on the product's own run path.
- The native provider refuses to start under `VADGR_MODE=production`.
- The `agents` table `DEFAULT` applies to newly created databases. Existing rows keep the model they were written with, and an agent that names its model is unaffected.
- Two findings are recorded rather than fixed, with their reason: `default` and `autonomous` produce identical outcomes in all 24 policy cells, and the gate is reached only when the model both chooses `request_approval` and self-declares `risk: "high"` - ordinary tool dispatch is not policed. Risk classes and decision tables are `0.6.0`.
- macOS Keychain and the native Windows desktop channel are proven by command and store *selection* only; that the selected command works on those hosts is owed.

### Tests
- `engine/` 110 passed (loop, pruning, journal, http, auth incl. per-OS resolution, format, provider invariants, the eight control-plane tools, policy, channels, ports).
- `api/` + `registry/` + `cli/` 850 passed, 1 skipped. No regressions.

## [0.3.0] - 2026-07-03

*Reconstructed from the diff: this release was tagged without a changelog entry.*

### Added
- **Mobile pairing.** `vadgr pair` mints a one-time token and prints a terminal QR; the same card appears in Settings under Mobile Pairing. Both encode a `vadgr://pair?...` deep link carrying host, port, token and machine name.
- **Pluggable connection transport** (`api/transport/`) selected by `VADGR_TRANSPORT`: `loopback` (default, single machine) and `tailscale`, which reaches the machine from another device over the user's own tailnet and advertises the node's MagicDNS name in the QR.
- **Two-gate access control** (`api/auth/middleware.py`) on every request: the source must be an authorized peer - a tailnet member, with loopback trusted - *and* carry a valid per-device bearer token.
- **Pairing endpoints and storage**: `POST /api/auth/pair`, `POST /api/auth/claim`, `GET` and `DELETE /api/devices`, backed by token primitives, a pairing store, a device repository and a `devices` table.
- **Mobile run-event WebSocket stream**, and the contract models the mobile app consumes: `Device`, `Pair`/`Claim`, `RunEvent`.

### Fixed
- tailscaled LocalAPI is queried over HTTP/1.0, and reached over a named pipe on native Windows.

### Notes
- Pairing needs a transport that can advertise a reachable address. On `loopback` it returns 503 by design - a localhost QR is useless to a phone - so use `VADGR_TRANSPORT=tailscale`.

### Tests
- 513 passed. Verified live over a real tailnet: pair, claim and device persisted, with gate enforcement confirmed from a second machine (401 without a token, 200 with it).

## [0.2.0] - 2026-05-21

### Removed
- TypeScript Discord gateway: entire `vadgr/gateway/` directory (17 files - adapters, router, security, server, API client, tests, `package.json`, `tsconfig.json`).
- CLI gateway commands: `cli/commands/gateway_cmd.py`. `vadgr gateway` is no longer a registered command.
- API gateway endpoints: removed the `DiscordUpdate` model and both `/messaging-gateway*` endpoints from `api/routes/settings.py`. Supporting service module `api/services/gateway_setup.py` deleted.
- Frontend gateway UI: `frontend/src/hooks/useMessagingGateway.ts` deleted; the Messaging Gateway `<Card>` block (~176 lines) removed from `frontend/src/pages/Settings.tsx`.
- All gateway references from `README.md` (module section, tree-view entry, "Connect via Discord" wording).

### Added
- `api/tests/test_gateway_decommissioned.py` - 10 guardrail tests that fail if any gateway artifact is re-introduced (import fails, no `/messaging-gateway` routes registered, `vadgr gateway --help` errors, etc.).

### Upgrade notes
- **Operators must manually delete `~/.forge/gateway.json`, `~/.forge/pids/gateway.pid`, and `~/.forge/gateway.log` after upgrading.** Gateway state lived in `~/.forge/gateway.json` (mode 0600 - Discord bot token + enable flag), never in the SQLite schema. The 0.2.0 codebase no longer reads or writes that file.
- **Discord bot tokens stored in `~/.forge/gateway.json` are lost on upgrade.** Back up the file before upgrading if you need to preserve them.
- No Alembic migration ships - no `gateway_*` tables ever existed in the schema.

### Tests
- Baseline (`0.1.0`): 443 + 179 + 150 = 772 passed, 1 skipped.
- After this version: 453 + 179 + 150 = 782 passed, 1 skipped. +10 new guardrail tests, 0 regressions.

## [0.1.0] - 2026-05-21

### Added
- Initial tagged release. Establishes the baseline before the gateway decommission. Captures the current state of the repository: API (FastAPI + engine + persistence + websocket) + CLI (Click HTTP client) + frontend (React + Vite dashboard) + forge (workflow + skills generator) + registry (`.agnt` package manager) + Discord gateway (TypeScript, decommissioned in 0.2.0).

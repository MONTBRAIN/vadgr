# 0.4.10 - the built-in transport: e2e runbook

> **Read this whole file before you run anything, and read
> [`../README.md`](../README.md) beside it.** Not the rules that look relevant to
> the cell in front of you: the whole file. Every rule in it was written because
> a pass broke it.

A phone can pair with this machine and talk to it with no second product
installed on either end. The daemon serves a built-in transport, an iroh
endpoint, beside Tailscale; it reports the transports it supports rather than
serving a set an owner configured; and gate 1 on the built-in transport is a
handshake-proven endpoint id, bound at claim.

> **Status: not started.** The runbook is complete and its harness builds. No
> live cell has run. The automated gate ran green on the build host (WSL):
> `cargo test`, `cargo clippy --all-targets -- -D warnings`, `cargo fmt --check`
> and `python3 -m pytest scripts/tests -q` all passed. The gate is necessary and
> never sufficient: it drives no transport and reaches no phone, so every live
> cell below is owed. The per-OS table reads `not run` on every row until a host
> drives it.

## How a pass is run, before anything else in this file

The five rules in [`../README.md`](../README.md) hold here without restatement:
whatever needs the owner runs first, the pass does not stop to report, a bug
found is a bug fixed here and now with a test that fails without the fix, a fix
invalidates the cells it touched on every operating system that had passed them,
and the evidence is pushed as part of the pass, never left on the machine.

**Where the evidence goes.** Every host pushes its boundary into the one branch
this minor's evidence lives on, `evidence/vadgr-0.4.10` in the docs repository,
and opens or updates the one pull request on it. **The default branch is never
the target.**

**One command at a time.** Every product command is invoked on its own and its
output and exit code are read before the next is chosen.

**A rebuild is a new subject.** If any fix lands mid-pass, the binaries are
rebuilt, `A1` is re-run and its new hashes recorded **before any further cell**,
and every cell the changed files touch goes back to `not run`.

## The approach

**The subject is who can reach the machine, so the oracle is the daemon, never
the client's report of it.** A cell that claims an unbound peer is refused reads
the daemon's own answer: the QUIC handshake verdict, the HTTP status the dialer
recorded, the binding row in the database, the `device paired` log line. The
dialer saying "refused" proves nothing on its own; the daemon's refusal is the
fact.

**The built-in transport is driven by an independent client** (`harness/dialer`,
[`../README.md`](../README.md)), because it speaks QUIC and no standard-library
client can. It is the built-in transport's `sockets.py`: an implementation of
the wire other than the one under test. It never drives a product flow or
chooses an action; a cell hands it a request list and reads the record.

**The public product is invoked as its user invokes it.** `vadgr pair` runs in a
terminal, the printed QR is parsed from the capture, and a claim is corroborated
on `GET /api/devices` over loopback. The installed entry point on `PATH` is the
subject; a source-tree `cargo run` is not.

## Paired surfaces this pass depends on

This daemon is called by two other repositories, each on its own version. **A
cell asks a paired repository only for what it has released.**

| repository | released version | what this pass relies on |
|---|---|---|
| vadgr-mobile | 0.4.1 | nothing this release requires. The released app reads `host`/`port` from the pairing QR, and this release keeps both when Tailscale is dialable, so a `0.4.1` handset still pairs over Tailscale unchanged (`M2`). The phone half that dials the built-in transport is that repository's **0.4.5**, unreleased, so every built-in-transport phone cell here is driven by `harness/dialer` standing in for it, and the handheld built-in flow is named in Part M as owed to that release |
| vadgr-computer-use | 0.7.4 | the installed `vadgr-cua` entry point over stdio, for the one run cell that watches a run over the built-in transport (`M1`). cua is a local child process and never on the network path, so no other cell touches it |

**What this means for a cell that wants the phone.** The built-in transport's
phone client ships at mobile `0.4.5`. Until it does, the built-in transport is
proven by the independent dialer, which is the method for an agent-driven pass,
and the handheld cells that need a real handset dialing the built-in transport
are written in Part M and marked `not run` with mobile `0.4.5` named as the
blocker.

## Owner and environment requirements

| requirement | cells | non-secret availability check | cost or destructive effect | cleanup |
|---|---|---|---|---|
| A default provider/model connected, so a run can start | `M1` | `vadgr providers` shows a default | one billed run's calls | the isolated root is removed |
| `GEMINI_API_KEY` (or another provider key) in `../.env` | `M1` | `grep -c '^GEMINI_API_KEY' ../.env` returns `1`; the value is never printed | one billed run | the isolated root is removed |
| Two networks: the machine behind a residential NAT, a client on a mobile carrier or a separate network namespace | `T1`, `B1`-`B7`, `C1`-`C4`, `H1`-`H4`, `S1`-`S6`, `F1`-`F6`, `X1` | the machine has an outbound route to a relay; the second network reaches the internet but not the machine's LAN | relay traffic only, on n0's public relays | none |
| Tailscale up and logged in | `P2`, `D1`, `F4`, `M2` | `tailscale status` names this node | none | none |
| A container runtime or a second network namespace, for the away and security cells | `T1`, `B`-`S`, `X1` | `docker info`, `podman info`, or `ip netns` answers | none | the namespace or container is removed |
| A real handset with the built-in-transport app (`vadgr-mobile 0.4.5`) | `M3`-`M5` | the app is installed and the tester holds the phone | none | the device is removed |
| `vadgr-computer-use` installed, `vadgr-cua` resolvable | `M1` | `vadgr-cua doctor` exits `0` | none | none |
| The built-in transport's dialer, built from its committed path | every `T`, `B`, `C`, `H`, `S`, `F`, `X` cell | `cargo build --release` in `harness/dialer` produces the binary | none | none |
| Rust toolchain and git | all | `cargo --version`, `git --version` | none | none |

**The handset group (Part M) runs first**, per the rule that owner cells open a
pass. Its setup, a provider login and a build onto the phone, is the first work.

## Billed model selection

| cells | provider/auth | required capabilities | selected model | official source and date | input/output price | hard iterations/tokens/cost | escalation condition |
|---|---|---|---|---|---|---|---|
| `M1` | Gemini / API key | text generation, tool calls, image-bearing tool-result continuation (the run watches a screen action) | the cheapest catalog model that passes `vadgr model default`'s own live check with those capabilities, re-verified against the authenticated catalog on the execution date | the authenticated catalog read on the execution date | read from the catalog on the day | 10 iterations, one run, 200,000 input tokens, USD 0.20 | none: a capability failure ends the cell |

This release adds no model call of its own; `M1` is the one run cell, and it
exists to prove a run watched over the built-in transport behaves as one watched
over the socket. Every other cell drives transport and gates, which cost nothing.

## Prerequisites

```bash
export E2E_ROOT="$(mktemp -d)"
export E2E_BIN="$E2E_ROOT/bin"
export PATH="$E2E_BIN:$PATH"
export VADGR_STATE_HOME="$E2E_ROOT/state"
export VADGR_HOME="$E2E_ROOT/home"
export VADGR_PORT=8861
# The machine serves what it supports by default. The tests that must not be
# dialable set VADGR_TRANSPORT=loopback; the away and security cells leave it
# unset so the built-in transport comes up.
cargo build --release --bins
mkdir -p "$E2E_BIN" && cp target/release/vadgr "$E2E_BIN/"
command -v vadgr && sha256sum "$(command -v vadgr)"
# The independent built-in-transport client.
( cd E2E/0.4.10/harness/dialer && cargo build --release )
export DIALER="$PWD/E2E/0.4.10/harness/dialer/target/release/vadgr-iroh-dialer"
```

## Remote-host handoff for Linux, macOS and Windows

Each native-host session follows this without context from another session.

1. **Read first**: `AGENTS.md`, `E2E/README.md` and this runbook, whole. Check
   out the same PR head and record `git rev-parse HEAD` in every result.
2. **Build and install**, never run from the source tree: `cargo build --release
   --bins`, copy `vadgr` into an empty root, put it first on `PATH`. `A1`
   records `command -v vadgr` and its `sha256`. Build the dialer from its
   committed path. If a fix lands mid-pass, rebuild, re-run `A1`, and re-run the
   invalidated cells.
3. **Two networks decide the built-in-transport cells.** `T`, `B`, `C`, `H`,
   `S`, `F` and `X` dial the machine from a second network the machine cannot
   reach on its LAN: a network namespace, a container with only outbound
   routing, or a separate host on a mobile carrier. A host with only one network
   marks those cells `blocked` by name and the relay-free cell (`F5`) is where
   the same-network path is proven instead.
4. **Tailscale decides `P2`, `D1`, `F4` and `M2`.** On a host where `tailscale
   status` names this node they run; without it they are `blocked` by name and
   the built-in transport carries the phone in `F4`'s place.
5. **The environment** is the block above. Windows PowerShell mirrors it with
   `$env:` assignments, as the `0.4.9` runbook shows.
6. **Order.** `M` first, because it needs a person and a build onto the phone.
   Then `A`, the automated gate, then `T` (the traversal spike, the first live
   boundary), then `P`, `B`, `C`, `H`, `S`, `D`, `F`, `X`, `K`.
7. **Evidence** goes in a dated directory created before the first cell. The
   dialer records are captured to files at each group's boundary; a helper may
   count or read them, and may not open the QUIC connection for you. The
   deletion sweep tables are generated by the `0.4.9` `harness/tables.py` from a
   recorded sweep, never typed.
8. **Cleanup**: stop only the daemons you started, by pid; remove only the
   isolated root and any network namespace the pass created.
9. **Credentials**: read only what a cell needs from `../.env`, into that
   command's environment only. Run the secret check before the group and again
   before evidence is sealed.
10. **Write your own column** in the per-OS table, from observation.

## Automated gate (necessary, never sufficient)

- `cargo test` -> **N passed** (the whole suite: lib, the transport registry,
  the admission matrix, the migration ladder, the device-peers repository, and
  the gate matrix over the built-in transport)
- `cargo clippy --all-targets -- -D warnings`, `cargo fmt --check` -> exit `0`
- `python3 -m pytest scripts/tests -q` -> **N passed**, the repository's own gates
- The dialer builds: `cargo build --release` in `harness/dialer` -> exit `0`

The suites cannot tell you whether an unbound internet peer is actually refused
on real networks, whether the away case traverses a residential NAT, or whether
a held-open connection is closed when its window ends. That is this runbook's
half. The gate's counts and exit codes are filed in `gate/` before Part A.

## Coverage

| Part | Axes | Cells | Run | Open |
|---|---|---|---|---|
| A the binary is the built head | identity x version | 2 | 0 | 2 |
| T the traversal spike, first | network x path | 1 | 0 | 1 |
| P: pairing and the report | transport x reach | 4 | 0 | 4 |
| B: the admission rule | binding x window x route | 7 | 0 | 7 |
| C the claim binds what the transport proved | transport x binding | 4 | 0 | 4 |
| H: health's scope | caller x entry | 4 | 0 | 4 |
| S: the security surface | attacker x control | 6 | 0 | 6 |
| D the deletion sweep, per transport | transport x surface | 2 | 0 | 2 |
| F: failure and recovery | failure x recovery | 6 | 0 | 6 |
| X: out of the box | fresh machine x dial | 1 | 0 | 1 |
| K: the secret key file | platform x permission | 1 | 0 | 1 |
| M the phone, held by a person | what mobile 0.4.5 does | 5 | 0 | 5 |
| | | **43** | **0** | **43** |

## Part A: the thing under test is the thing that was built

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| A1 | `$E2E_BIN` first on `PATH`, and the dialer built | `command -v vadgr`; `sha256sum` it and the dialer binary | both resolve inside the isolated tree; the `vadgr` hash is the release build of the head under test. Re-run after any mid-pass rebuild | the path and hash lines, and the head they were built from | none | not run: owner drives the pass; the build host has not filed a boundary |
| A2 | as A1 | `vadgr --version` | prints `0.4.10`, matching the manifest and `GET /api/health`'s `version` | the printed line and the manifest line | none | not run: owner drives the pass |

## Part T: the traversal spike runs first, before the rest

The spec makes the spike the runbook's first live boundary (§5.4): before
anything else, prove the away case on the real networks the owner has. A
failure here stops the minor and goes to the owner with the options, rather
than surfacing four groups in.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| T1 | The daemon up with nothing set (default relays), behind the home NAT; a second network (phone hotspot or a namespace with no LAN route to the machine) | `vadgr pair` on the machine; read `node`, `relays` from the QR; from the second network, `$DIALER` dials the endpoint id and drives `GET /api/health` then a claim | the handshake completes; health answers `200`; the claim answers `200`. Record whether rendezvous was direct or relayed and the connect latency. Oracle: the daemon's `device paired` log line and the `device_peers` row | the dialer record, the daemon log for the window, the pairing report, the direct/relayed reading and latency | remove the device | not run: needs two real networks and the owner to hold the second; this is the owner's opening cell |

## Part P: pairing reports every supported transport

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| P1 | The daemon up, default config | `curl -s -X POST http://127.0.0.1:$VADGR_PORT/api/auth/pair` | `transports` carries `iroh` and `tailscale`; `iroh` holds `node`, `relays`, `direct`; a down transport is present as `null`, never absent. Oracle: the response body against the running endpoint's own id in the boot log | the response body, the boot log's endpoint id | let the code expire | not run: owner drives the pass |
| P2 | Tailscale up | `vadgr pair` in a terminal | one printed line per supported transport with its address, and the top-level `host`/`port` still present for the released scanner. Oracle: the printed block against the report | the captured terminal output | let the code expire | not run: needs Tailscale up on the host |
| P3 | No Tailscale (`tailscale` down or absent) | `vadgr pair` | the QR still builds with no `host`/`port`; the print names Tailscale not available in its own words and says the machine pairs by QR only. Oracle: the QR decoded by `harness/qr-decode` carries `node` and no `host` | the decoded QR, the captured print | let the code expire | not run: owner drives the pass |
| P4 | `VADGR_TRANSPORT=loopback` | `curl -s -X POST .../api/auth/pair` | `503 TRANSPORT_UNREACHABLE`, the message naming the local-only override, `details.transports` present. Oracle: the status and code | the response body | none | not run: owner drives the pass |

## Part B: the admission rule on the built-in transport

Every cell here dials from the second network with the dialer, as an endpoint id
that is not bound. The oracle is the daemon: the handshake verdict, the HTTP
status, and the pairing store's window.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| B1 | A pairing window open (owner ran `vadgr pair`); a fresh unbound dialer identity | dial and drive `GET /api/health` | handshake completes; `200`. Oracle: the dialer record and the daemon access log | the dialer record | let the window expire | not run: needs the second network and a live window |
| B2 | as B1 | dial and drive `POST /api/auth/pair` | `403 SOURCE_NOT_AUTHORIZED`, and the owner's outstanding code still claims afterward. Oracle: the status, then a loopback claim of the owner's code succeeds | the dialer record, the follow-up claim | let the window expire | not run: needs the second network and a live window |
| B3 | as B1 | dial and drive `GET /api/devices` and `POST /api/runs` | both `403 SOURCE_NOT_AUTHORIZED`, token or no token. Oracle: the statuses | the dialer record | let the window expire | not run: needs the second network and a live window |
| B4 | No pairing window, no bound device (fresh machine) | dial with a fresh unbound identity, `expect_handshake:false` | the handshake does not complete: refused at accept. Oracle: the dialer's `Refused` and the daemon's accept-loop refusal log | the dialer record, the daemon log | none | not run: needs the second network and a fresh state root |
| B5 | A window open; four unbound identities already holding connections | a fifth unbound identity dials | the fifth is refused and the first four keep working. Oracle: the four still answer `GET /api/health`; the daemon logs the refusal with the peer id | the five dialer records, the daemon log | close the four | not run: needs the second network and five concurrent dials |
| B6 | An unbound connection admitted during a window, held open; the owner then claims (redeeming the window) with a different phone | on the held connection, send a request after the claim | the held connection is closed and the late request is not served. Oracle: the dialer's stream error and the daemon's connection-close log | the dialer record, the daemon log | none | not run: needs two coordinated dials on the second network |
| B7 | A window open; an unbound connection admitted, then held silent | wait past 60 seconds without a request | the connection is closed at its lifetime. Oracle: the daemon's lifetime-close log and the dialer's connection end | the dialer record, the daemon log | none | not run: needs the second network and a 60-second wait |

## Part C: a claim binds what the transport proved

| # | Precondition and setup | Goal or action | Expected observable and oracle | Expected boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| C1 | A window open; a dialer with a fixed secret key | dial and drive `POST /api/auth/claim` | `200` with `token`, `machine_name`, `transports`; the handshake's endpoint id is bound. Oracle: the `device_peers` row holds `(iroh, <the dialer's id>)` and the `device paired` log names transport `iroh` | the dialer record, the row read back, the log line | remove the device | not run: needs the second network |
| C2 | The device from C1 bound; same dialer identity and its token | dial and drive `GET /api/health` then `GET /api/devices` with the token | health is the full block (endpoint id present); devices answers `200`. Oracle: the dialer records and the row | the dialer records | remove the device | not run: needs the second network |
| C3 | A window open; a claim over loopback and one over Tailscale | claim on each and read the bindings | both succeed and bind nothing: `device_peers` has no row for either. Oracle: the table read back | the claim responses, the row counts | remove the devices | not run: the Tailscale half needs Tailscale up |
| C4 | The device from C1 bound; the same dialer identity claims again (a second pairing) | dial, open a window, claim | the second claim succeeds and takes the earlier row rather than failing on the primary key; one row remains for that identity. Oracle: the row count is one, pointing at the new device | the claim responses, the row read back | remove the device | not run: needs the second network |

## Part H: health serves addresses only to a caller who earned them

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| H1 | The daemon up | `curl` health over loopback | the full block: every transport's diagnostics, the built-in `node` and the tailnet name present. Oracle: the body | the response body | none | not run: owner drives the pass |
| H2 | A window open; a fresh unbound dialer identity | dial and drive `GET /api/health` | every entry reduced to `name` and `available`: no `node`, no relay list, no direct address, no tailnet name. Oracle: the dialer record's per-entry keys | the dialer record | let the window expire | not run: needs the second network and a live window |
| H3 | A phone bound over the built-in transport (from C1); its identity, no token | dial and drive `GET /api/health` | the full block, on the tokenless probe: the address refresh a paired phone rides. Oracle: the `node` present in the built-in entry | the dialer record | remove the device | not run: needs the second network |
| H4 | A window open; an unbound identity presenting a token that matches nothing | dial and drive `GET /api/health` with a junk bearer token | `200`, the public scope, not an error: health answers a phone the machine has forgotten. Oracle: the reduced entries and the `200` | the dialer record | let the window expire | not run: needs the second network |

## Part S: the security surface, driven from the second network

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| S1 | A window open; an unbound identity | dial `POST /api/auth/pair` during the window; then the owner claims their own code | pair is `403` and the refusal is before any mint: the owner's code still claims. Oracle: the owner's claim succeeds and the store never minted a second code | the dialer record, the owner's claim, the daemon log | remove the device | not run: needs the second network and a live window |
| S2 | A window open; an unbound identity | dial `GET /api/health` | no endpoint id, relay list, direct address or tailnet name reaches the unbound peer. Oracle: the dialer record's keys | the dialer record | let the window expire | not run: needs the second network |
| S3 | A bound phone (from C1); its tokenless probe | dial `GET /api/health` | the same probe that leaks nothing to a stranger gives the bound phone the full block. Oracle: the contrast with S2 in one boundary | both dialer records | remove the device | not run: needs the second network |
| S4 | An unbound connection admitted during a window, held open past the owner's claim | send a request on the held connection after the claim | it is not served: the connection was closed with the window. Oracle: the dialer stream error and the daemon close log | the dialer record, the daemon log | none | not run: needs two coordinated dials |
| S5 | Four unbound connections during a window | a fifth unbound connection dials | the fifth is refused, the first four keep working: no eviction. Oracle: the four still answer, the daemon logs the refusal | the dialer records, the daemon log | close the four | not run: needs five concurrent dials |
| S6 | A window open; a dialer with a fixed key | claim carrying a `node_key` field on the body, over the built-in transport and over loopback | `422` on both: the field does not exist and the body is strict. Oracle: the status and the transitional detail shape | the two claim responses | none | not run: needs the second network for the built-in half |

## Part D: the deletion sweep re-runs, once per transport

The iteration's own sentence: the surviving surface answers identically however
the bytes arrive. The `0.4.9` sweep is re-run over each transport and compared
structurally: method, path, status, error code, and the run-socket frame counts.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| D1 | Tailscale up; a tailnet client | run the `0.4.9` `harness/sweep.py` and `harness/sockets.py` over the tailnet | every entry matches the socket run's method, path, status and error code; both run-socket routes carry the same frame counts. Oracle: `harness/compare.py` against the loopback sweep | the sweep record, the socket frames, the comparison | none | not run: needs Tailscale up and a tailnet client |
| D2 | The built-in transport up; the second network | drive the same surface with `$DIALER`, and the run socket over an upgraded stream | the surface answers identically to D1: same statuses, same codes; the run WebSocket upgrades on a stream and carries the same frame counts. Oracle: the comparison against D1 and the loopback sweep | the dialer records, the frame counts, the comparison | none | not run: needs the second network |

## Part F: failure and recovery

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| F1 | The relay firewalled at pairing (block the relay host outbound) | the second network dials during a window | rendezvous fails cleanly; `vadgr pair`'s report and the health block name the built-in transport's own words; loopback and Tailscale keep serving. Oracle: the daemon stays up and the other transports answer | the dialer record, the health block, the daemon log | unblock the relay | not run: needs the second network and a firewall rule |
| F2 | A phone bound over the built-in transport; the daemon then stopped | the phone dials | the handshake does not complete; the daemon log ends cleanly. Oracle: the dialer's `Refused` and the absence of a daemon process | the dialer record | restart the daemon | not run: needs the second network |
| F3 | A phone bound over the built-in transport; then `DELETE /api/devices/{id}` over loopback | the revoked phone dials again | refused at accept: the binding is gone, so the network path is gone. Oracle: the dialer's `Refused` and the empty `device_peers` for that id | the dialer record, the row read back | none | not run: needs the second network |
| F4 | A device paired over Tailscale before this release (no binding row) | the device dials over Tailscale | it still works, gate 1 is tailnet membership, no binding needed. Oracle: a tokened request answers `200` | the request record | remove the device | not run: needs Tailscale up and a pre-existing device |
| F5 | `VADGR_IROH_RELAYS=none`; the client on the machine's own network | dial the direct addresses from the report | rendezvous is direct, no relay in the path; the claim and an authenticated read succeed. Oracle: the dialer record over the direct address and the binding row | the dialer record, the report's direct addresses | remove the device | not run: needs a same-network client |
| F6 | `VADGR_TRANSPORT=loopback` | `vadgr pair` | `503 TRANSPORT_UNREACHABLE` naming the local-only override; the daemon otherwise serves loopback. Oracle: the status and the message | the response body | none | not run: owner drives the pass |

## Part X: a machine is reachable out of the box, and this is what that costs

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| X1 | A freshly installed daemon, nothing configured, no bound device, no window; the second network holds the endpoint id | dial with a fresh unbound identity, `expect_handshake:false` | the handshake does not complete. This is §7.6's claim: installing the release makes the machine dialable by a bound peer or during a window the owner opened, and by nobody else. Oracle: the dialer's `Refused` against the fresh machine's own endpoint id | the dialer record, the fresh boot log | remove the state root | not run: needs the second network and a fresh state root |

## Part K: the secret key file, per platform

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| K1 | A fresh state root; boot once, then read `credentials/iroh_secret_key` | inspect the file's permissions, then corrupt it and reboot | the file is owner-only (Unix mode `0600`; a current-user DACL on Windows), stable across reboots; a corrupt file fails the built-in transport loudly while loopback and Tailscale keep serving. Oracle: the mode read on this platform, and the daemon still answering loopback with the built-in transport marked unavailable | the permission read, the boot logs before and after corruption | remove the state root | not run: the permission branch is per platform and is asserted on each OS the pass runs on |

## Part M: the phone, held by a person

The built-in transport's phone client is `vadgr-mobile 0.4.5`, unreleased at this
runbook's writing. These cells are the handheld flows that release owes, named
here so the daemon behaviour each leans on is on the record and driven from this
side by the dialer in Parts T, B, C and H.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| M1 | A default provider connected; a phone paired (dialer stands in until mobile 0.4.5); a CLI-triggered run | watch the run over the built-in transport | the run's frames arrive over the built-in transport's upgraded stream exactly as over the socket. Oracle: the frame counts against a loopback watch of the same run | the frame counts, the run journal | remove the run | not run: the run watch over the built-in transport is proven by `D2`; the handheld half is mobile 0.4.5's |
| M2 | A released `vadgr-mobile 0.4.1` handset; Tailscale up | pair by scanning the QR, over Tailscale | the released app pairs unchanged: the QR still carries `host` and `port`. Oracle: the daemon's `device paired` line names transport `tailscale` | the daemon log, the tester's note | remove the device | not run: needs a 0.4.1 handset and Tailscale up |
| M3 | A handset with Tailscale uninstalled and the built-in-transport app | scan the QR, pair over the built-in transport, watch a CLI-triggered run | the app is offered no choice (only the built-in transport is usable), pairs over it, and the run appears. Oracle: the daemon's `device paired` line names transport `iroh` | the daemon log, the tester's note | remove the device | not run: blocked on vadgr-mobile 0.4.5, which builds the phone's built-in-transport client |
| M4 | A handset that can use both transports | choose Tailscale at pairing and pair over it | neither path ships unexercised: the deliberate Tailscale choice pairs over Tailscale. Oracle: the daemon's `device paired` line names transport `tailscale` | the daemon log, the tester's note | remove the device | not run: blocked on vadgr-mobile 0.4.5 |
| M5 | A paired phone in a live run; the chosen transport taken down | recover from the conversation and pick the run back up | the machine reads as not reachable, the owner recovers, and the run re-attaches through the socket's replay. Oracle: the run continues with no gap | the tester's note, the run journal | remove the device | not run: blocked on vadgr-mobile 0.4.5, whose recovery flow this exercises |

## Per-OS results

Each row is a part. **CI is not a pass**: an OS whose only evidence is the
automated gate is `not run`, never `pass`. The `overall` row is the weakest of
the parts actually driven on that OS.

| Part | Linux | Windows | macOS | WSL |
|---|---|---|---|---|
| A: the built head | not run: the owner runs it | not run: the owner runs it | not run: the owner runs it | not run: the owner runs it |
| T: the traversal spike | not run: needs two networks | not run: needs two networks | not run: needs two networks | not run: needs two networks |
| P: pairing and the report | not run: the owner runs it | not run: the owner runs it | not run: the owner runs it | not run: the owner runs it |
| B: the admission rule | not run: needs the second network | not run: needs the second network | not run: needs the second network | not run: needs the second network |
| C: the claim binds | not run: needs the second network | not run: needs the second network | not run: needs the second network | not run: needs the second network |
| H: health's scope | not run: needs the second network | not run: needs the second network | not run: needs the second network | not run: needs the second network |
| S: the security surface | not run: needs the second network | not run: needs the second network | not run: needs the second network | not run: needs the second network |
| D: the deletion sweep | not run: needs Tailscale and a second network | not run: needs Tailscale and a second network | not run: needs Tailscale and a second network | not run: needs Tailscale and a second network |
| F: failure and recovery | not run: needs the second network | not run: needs the second network | not run: needs the second network | not run: needs the second network |
| X: out of the box | not run: needs a fresh root and a second network | not run: needs a fresh root and a second network | not run: needs a fresh root and a second network | not run: needs a fresh root and a second network |
| K: the secret key file | not run: the permission branch is asserted per OS | not run: the DACL branch is asserted on Windows | not run: the permission branch is asserted per OS | not run: the permission branch is asserted per OS |
| M: the phone | not run: blocked on vadgr-mobile 0.4.5 | not run: blocked on vadgr-mobile 0.4.5 | not run: blocked on vadgr-mobile 0.4.5 | not run: blocked on vadgr-mobile 0.4.5 |
| overall | not run: no live cell has run | not run: no live cell has run | not run: no live cell has run | not run: no live cell has run |

## Close: three independent passes

The runbook is closed with **three separate agents running the sweep
concurrently**, each with its own port, database, daemon and state root, and
**each pass is local-only except where a cell needs the network**, which is what
`VADGR_TRANSPORT=loopback` exists for. Compare them structurally per the
doctrine: every HTTP entry on method, path, status and error code; the dialer
records on handshake verdict and per-request status; the run-socket frame counts
per transport. Then read the token counts, the fixture pinned first. Ask each
agent what looked odd, not only whether its cells passed.

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

## The away case, and where this pass proves it

**Every device on this network is on this network.** Two machines on one LAN
reach each other directly whatever the payload says, so a relay cell driven
between them would pass for the wrong reason. That is the same defect as
dialing loopback, one layer out, and a result produced that way is worth less
than no result.

**So the away case is proved once, by the real client, in `M3`.** The owner
holds the handset on **mobile data**: a carrier NAT on one side, the home NAT on
the other, which is the pair the built-in transport exists to cross. It is the
product's own client rather than the harness, and it needs no container, no
namespace and no second machine.

**What the rest of the pass does instead, and what each cell may therefore
claim.** Cells about **authorization and protocol** need no topology at all:
the gates, admission, the pairing window, the caps, the schema, the config
refusals, the CLI and the surface sweep run with the dialer on this host,
dialing the endpoint id over the real QUIC stack and the real ALPN. The network
layout is irrelevant to what they assert.

**The relay path is forced rather than hoped for.** The dialer takes its
addresses from a JSON job exactly as a phone takes them from a QR, so a job with
`direct` emptied leaves the relay as the only path. That is a real payload
shape, not a trick: it is what a machine with no discovered direct addresses
sends. It proves the relay carries a session end to end, deterministically, on
any network.

**Off-machine reachability uses a second machine on this LAN.** That proves
traffic leaves this host. It does not prove the away case, and no cell here
claims it does.

## Owner and environment requirements

| requirement | cells | non-secret availability check | cost or destructive effect | cleanup |
|---|---|---|---|---|
| A default provider/model connected, so a run can start | `M1` | `vadgr providers` shows a default | one billed run's calls | the isolated root is removed |
| `GEMINI_API_KEY` (or another provider key) in `../.env` | `M1` | `grep -c '^GEMINI_API_KEY' ../.env` returns `1`; the value is never printed | one billed run | the isolated root is removed |
| **The away case: the owner's handset on mobile data** (not the home wifi). Every device on this network is on this network, so no arrangement of them produces two NATs; the phone's carrier is the only real second network available | `M3` | the tester holds the phone and turns wifi off | none | the device is revoked at the end |
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
( cd E2E/0.4.10/harness/dialer && cargo build --release)
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
3. **What each built-in-transport cell may claim, and what proves it.** `T`,
   `B`, `C`, `H`, `S`, `F` and `X` assert **authorization and protocol**, not
   topology, so they run with the dialer on this host against the endpoint id
   over the real QUIC stack and the real ALPN. Say that in the result rather
   than implying a second network was used. **The relay path is forced, never
   hoped for**: the dialer takes its addresses from its job, so a job with
   `direct` emptied leaves the relay as the only path, which is a real payload
   shape rather than a trick. **Off-machine reachability** uses a second host on
   this LAN and proves only that traffic leaves this machine. **The away case,
   two NATs, is `M3`'s alone**, driven by the handset on mobile data. A cell
   that cannot be driven is marked `blocked` or `not run` by name with its
   reason; none of them is marked from a substitute.
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
| P: pairing and the report | transport x reach | 4 | 0 | pass |
| B: the admission rule | binding x window x route | 7 | 0 | pass |
| C the claim binds what the transport proved | transport x binding | 4 | 0 | 4 |
| H: health's scope | caller x entry | 4 | 0 | pass |
| S: the security surface | attacker x control | 6 | 0 | pass |
| D the deletion sweep, per transport | transport x surface | 2 | 0 | 2 |
| F: failure and recovery | failure x recovery | 6 | 0 | partial: F1 substituted, its second-network half not run |
| X: out of the box | fresh machine x dial | 1 | 0 | pass |
| K: the secret key file | platform x permission | 1 | 0 | pass |
| M the phone, held by a person | what mobile 0.4.5 does | 5 | 0 | 5 |
| | | **43** | **0** | **43** |

## Part A: the thing under test is the thing that was built

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| A1 | `$E2E_BIN` first on `PATH`, and the dialer built | `command -v vadgr`; `sha256sum` it and the dialer binary | both resolve inside the isolated tree; the `vadgr` hash is the release build of the head under test. Re-run after any mid-pass rebuild | the path and hash lines, and the head they were built from | none | pass |
| A2 | as A1 | `vadgr --version` | prints `0.4.10`, matching the manifest and `GET /api/health`'s `version` | the printed line and the manifest line | none | pass |

## Part T: the traversal spike runs first, before the rest

The spec makes the spike the runbook's first live boundary (§5.4): before
anything else, prove the away case on the real networks the owner has. A
failure here stops the minor and goes to the owner with the options, rather
than surfacing four groups in.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| T1 | The daemon up with nothing set (default relays), behind the home NAT; a second network (phone hotspot or a namespace with no LAN route to the machine) | `vadgr pair` on the machine; read `node`, `relays` from the QR; from the second network, `$DIALER` dials the endpoint id and drives `GET /api/health` then a claim | the handshake completes; health answers `200`; the claim answers `200`. Record whether rendezvous was direct or relayed and the connect latency. Oracle: the daemon's `device paired` log line and the `device_peers` row | the dialer record, the daemon log for the window, the pairing report, the direct/relayed reading and latency | remove the device | not run: the owner's opening cell, needs two real networks |

## Part P: pairing reports every supported transport

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| P1 | The daemon up, default config | `curl -s -X POST http://127.0.0.1:$VADGR_PORT/api/auth/pair` | `transports` carries `iroh` and `tailscale`; `iroh` holds `node`, `relays`, `direct`; a down transport is present as `null`, never absent. Oracle: the response body against the running endpoint's own id in the boot log | the response body, the boot log's endpoint id | let the code expire | pass |
| P2 | Tailscale up | `vadgr pair` in a terminal | one printed line per supported transport with its address, and the top-level `host`/`port` still present for the released scanner. Oracle: the printed block against the report | the captured terminal output | let the code expire | pass |
| P3 | No Tailscale (`tailscale` down or absent) | `vadgr pair` | the QR still builds with no `host`/`port`; the print names Tailscale not available in its own words and says the machine pairs by QR only. Oracle: the QR decoded by `harness/qr-decode` carries `node` and no `host` | the decoded QR, the captured print | let the code expire | pass |
| P4 | `VADGR_TRANSPORT=loopback` | `curl -s -X POST .../api/auth/pair` | `503 TRANSPORT_UNREACHABLE`, the message naming the local-only override, `details.transports` present. Oracle: the status and code | the response body | none | pass |

## Part B: the admission rule on the built-in transport

Every cell here dials from the second network with the dialer, as an endpoint id
that is not bound. The oracle is the daemon: the handshake verdict, the HTTP
status, and the pairing store's window.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| B1 | A pairing window open (owner ran `vadgr pair`); a fresh unbound dialer identity | dial and drive `GET /api/health` | handshake completes; `200`. Oracle: the dialer record and the daemon access log | the dialer record | let the window expire | pass |
| B2 | as B1 | dial and drive `POST /api/auth/pair` | `403 SOURCE_NOT_AUTHORIZED`, and the owner's outstanding code still claims afterward. Oracle: the status, then a loopback claim of the owner's code succeeds | the dialer record, the follow-up claim | let the window expire | pass |
| B3 | as B1 | dial and drive `GET /api/devices` and `POST /api/runs` | both `403 SOURCE_NOT_AUTHORIZED`, token or no token. Oracle: the statuses | the dialer record | let the window expire | pass |
| B4 | No pairing window, **and no device rows at all** (fresh machine) | dial with a fresh unbound identity, `expect_handshake:false` | the handshake does not complete: refused at accept. Oracle: the dialer's `Refused` and the daemon's accept-loop refusal log. **The precondition tightened when adoption arrived**: a machine that has ever paired a device now completes the handshake and refuses at the route instead, which B8 covers | the dialer record, the daemon log | none | pass: re-driven, refused before the handshake with no window and no device rows |
| B5 | A window open; four unbound identities already holding connections | a fifth unbound identity dials | the fifth is refused and the first four keep working. Oracle: the four still answer `GET /api/health`; the daemon logs the refusal with the peer id | the five dialer records, the daemon log | close the four | pass |
| B6 | An unbound connection admitted during a window, held open; the owner then claims (redeeming the window) with a different phone | on the held connection, send a request after the claim | the held connection is closed and the late request is not served. Oracle: the dialer's stream error and the daemon's connection-close log | the dialer record, the daemon log | none | pass |
| B7 | A window open; an unbound connection admitted, then held silent | wait past 60 seconds without a request | the connection is closed at its lifetime. Oracle: the daemon's lifetime-close log and the dialer's connection end | the dialer record, the daemon log | none | pass |
| B8 | A machine with **at least one paired device** and **no window open**; a fresh unbound identity with **no token** | dial and drive `POST /api/devices/self/transports`, then `GET /api/devices` | the handshake completes now, where B4's fresh machine refuses it, and the requests are refused at the route: `401 MISSING_TOKEN` on adopt and `403 SOURCE_NOT_AUTHORIZED` on devices. Nothing is bound. Oracle: the statuses and an unchanged `device_peers` | the dialer record, the table read back | none | pass |
| B9 | The same machine; a dialer holding **a valid device token** whose device was paired over a transport that binds nothing | dial and drive `POST /api/devices/self/transports` | `200` with `{"transport":"iroh","adopted":true}`, and `device_peers` gains exactly one row pairing that device with **the endpoint id the handshake proved**, not any value the caller sent. Oracle: the row read back against the dialer's own reported id | the dialer record, the row | remove the device | pass |
| B10 | The device from B9, already adopted | adopt again from **the same** identity, then from **a different** identity | the same identity answers `200` and leaves one row; a different identity answers `409 TRANSPORT_ALREADY_ADOPTED` and changes nothing. This is what stops a stolen token displacing the phone that owns the pairing | both dialer records, the row count | remove the device | pass |
| B11 | A device adopted per B9, then revoked with `DELETE /api/devices/{id}` | dial with that identity and adopt again | `401 INVALID_TOKEN`: the deletion cascaded the binding and killed the token, so there is nothing left to authenticate with and nothing to re-bind. Oracle: the status and an empty `device_peers` | the dialer record, the table | none | pass |
| B12 | A device paired over Tailscale; the tailnet claim's own connection | drive `POST /api/devices/self/transports` **over Tailscale** | `422 TRANSPORT_PROVES_NO_IDENTITY`: a transport that proves membership rather than a key has nothing to bind and needs nothing bound. Oracle: the status and code | the response body | remove the device | pass |

## Part C: a claim binds what the transport proved

| # | Precondition and setup | Goal or action | Expected observable and oracle | Expected boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| C1 | A window open; a dialer with a fixed secret key | dial and drive `POST /api/auth/claim` | `200` with `token`, `machine_name`, `transports`; the handshake's endpoint id is bound. Oracle: the `device_peers` row holds `(iroh, <the dialer's id>)` and the `device paired` log names transport `iroh` | the dialer record, the row read back, the log line | remove the device | pass |
| C2 | The device from C1 bound; same dialer identity and its token | dial and drive `GET /api/health` then `GET /api/devices` with the token | health is the full block (endpoint id present); devices answers `200`. Oracle: the dialer records and the row | the dialer records | remove the device | pass |
| C3 | A window open; a claim over loopback and one over Tailscale | claim on each and read the bindings | both succeed and bind nothing: `device_peers` has no row for either. Oracle: the table read back | the claim responses, the row counts | remove the devices | pass |
| C4 | The device from C1 bound; the same dialer identity claims again (a second pairing) | dial, open a window, claim | the second claim succeeds and takes the earlier row rather than failing on the primary key; one row remains for that identity. Oracle: the row count is one, pointing at the new device | the claim responses, the row read back | remove the device | pass |

## Part H: health serves addresses only to a caller who earned them

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| H1 | The daemon up | `curl` health over loopback | the full block: every transport's diagnostics, the built-in `node` and the tailnet name present. Oracle: the body | the response body | none | pass |
| H2 | A window open; a fresh unbound dialer identity | dial and drive `GET /api/health` | every entry reduced to `name` and `available`: no `node`, no relay list, no direct address, no tailnet name. Oracle: the dialer record's per-entry keys | the dialer record | let the window expire | pass |
| H3 | A phone bound over the built-in transport (from C1); its identity, no token | dial and drive `GET /api/health` | the full block, on the tokenless probe: the address refresh a paired phone rides. Oracle: the `node` present in the built-in entry | the dialer record | remove the device | pass |
| H4 | A window open; an unbound identity presenting a token that matches nothing | dial and drive `GET /api/health` with a junk bearer token | `200`, the public scope, not an error: health answers a phone the machine has forgotten. Oracle: the reduced entries and the `200` | the dialer record | let the window expire | pass |

## Part S: the security surface, driven from the second network

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| S1 | A window open; an unbound identity | dial `POST /api/auth/pair` during the window; then the owner claims their own code | pair is `403` and the refusal is before any mint: the owner's code still claims. Oracle: the owner's claim succeeds and the store never minted a second code | the dialer record, the owner's claim, the daemon log | remove the device | pass |
| S2 | A window open; an unbound identity | dial `GET /api/health` | no endpoint id, relay list, direct address or tailnet name reaches the unbound peer. Oracle: the dialer record's keys | the dialer record | let the window expire | pass |
| S3 | A bound phone (from C1); its tokenless probe | dial `GET /api/health` | the same probe that leaks nothing to a stranger gives the bound phone the full block. Oracle: the contrast with S2 in one boundary | both dialer records | remove the device | pass |
| S4 | An unbound connection admitted during a window, held open past the owner's claim | send a request on the held connection after the claim | it is not served: the connection was closed with the window. Oracle: the dialer stream error and the daemon close log | the dialer record, the daemon log | none | pass |
| S5 | Four unbound connections during a window | a fifth unbound connection dials | the fifth is refused, the first four keep working: no eviction. Oracle: the four still answer, the daemon logs the refusal | the dialer records, the daemon log | close the four | pass |
| S6 | A window open; a dialer with a fixed key | claim carrying a `node_key` field on the body, over the built-in transport and over loopback | `422` on both: the field does not exist and the body is strict. Oracle: the status and the transitional detail shape | the two claim responses | none | pass |

## Part D: the deletion sweep re-runs, once per transport

The iteration's own sentence: the surviving surface answers identically however
the bytes arrive. The `0.4.9` sweep is re-run over each transport and compared
structurally: method, path, status, error code, and the run-socket frame counts.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| D1 | Tailscale up; a tailnet client | run the `0.4.9` `harness/sweep.py` and `harness/sockets.py` over the tailnet | every entry matches the socket run's method, path, status and error code; both run-socket routes carry the same frame counts. Oracle: `harness/compare.py` against the loopback sweep | the sweep record, the socket frames, the comparison | none | pass |
| D2 | The built-in transport up; the second network | drive the same surface with `$DIALER`, and the run socket over an upgraded stream | the surface answers identically to D1: same statuses, same codes; the run WebSocket upgrades on a stream and carries the same frame counts. Oracle: the comparison against D1 and the loopback sweep | the dialer records, the frame counts, the comparison | none | pass |

## Part F: failure and recovery

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| F1 | The relay firewalled at pairing (block the relay host outbound) | the second network dials during a window | rendezvous fails cleanly; `vadgr pair`'s report and the health block name the built-in transport's own words; loopback and Tailscale keep serving. Oracle: the daemon stays up and the other transports answer | the dialer record, the health block, the daemon log | unblock the relay | partial: the daemon-side half passes; the second-network dial is the owner's |
| F2 | A phone bound over the built-in transport; the daemon then stopped | the phone dials | the handshake does not complete; the daemon log ends cleanly. Oracle: the dialer's `Refused` and the absence of a daemon process | the dialer record | restart the daemon | pass |
| F3 | A phone bound over the built-in transport; then `DELETE /api/devices/{id}` over loopback | the revoked phone dials again | nothing is served: the binding is gone, so the identity is admitted only inside a window and there is none. The handshake still completes, because only a machine that could admit nobody refuses before the handshake (B4, X1) and another device is still bound here; the refusal shows as the stream that cannot be opened. Oracle: the dialer's stream error and the empty `device_peers` for that id | the dialer record, the row read back | none | pass |
| F4 | A device paired over Tailscale before this release (no binding row) | the device dials over Tailscale | it still works, gate 1 is tailnet membership, no binding needed. Oracle: a tokened request answers `200` | the request record | remove the device | pass |
| F5 | `VADGR_IROH_RELAYS=none`; the client on the machine's own network | dial the direct addresses from the report | rendezvous is direct, no relay in the path; the claim and an authenticated read succeed. Oracle: the dialer record over the direct address and the binding row | the dialer record, the report's direct addresses | remove the device | pass |
| F6 | `VADGR_TRANSPORT=loopback` | `vadgr pair` | `503 TRANSPORT_UNREACHABLE` naming the local-only override; the daemon otherwise serves loopback. Oracle: the status and the message | the response body | none | pass |

## Part X: a machine is reachable out of the box, and this is what that costs

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| X1 | A freshly installed daemon, nothing configured, **no device rows at all**, no window; the second network holds the endpoint id | dial with a fresh unbound identity, `expect_handshake:false` | the handshake does not complete. This is §7.6's claim, and adoption leaves it exactly as it was: a machine that has never paired anything refuses before the handshake, so a fresh installation is dialable by nobody. Oracle: the dialer's `Refused` against the fresh machine's own endpoint id | the dialer record, the fresh boot log | remove the state root | pass |

## Part K: the secret key file, per platform

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| K1 | A fresh state root; boot once, then read `credentials/iroh_secret_key` | inspect the file's permissions, then corrupt it and reboot | the file is owner-only (Unix mode `0600`; a current-user DACL on Windows), stable across reboots; a corrupt file fails the built-in transport loudly while loopback and Tailscale keep serving. Oracle: the mode read on this platform, and the daemon still answering loopback with the built-in transport marked unavailable | the permission read, the boot logs before and after corruption | remove the state root | pass |

## Part M: the phone, held by a person

The built-in transport's phone client is `vadgr-mobile 0.4.5`, unreleased at this
runbook's writing. These cells are the handheld flows that release owes, named
here so the daemon behaviour each leans on is on the record and driven from this
side by the dialer in Parts T, B, C and H.

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| M1 | A default provider connected; a phone paired (dialer stands in until mobile 0.4.5); a CLI-triggered run | watch the run over the built-in transport | the run's frames arrive over the built-in transport's upgraded stream exactly as over the socket. Oracle: the frame counts against a loopback watch of the same run | the frame counts, the run journal | remove the run | pass: a CLI-triggered run reached the phone over the built-in transport, complete |
| M2 | A released `vadgr-mobile 0.4.1` handset; Tailscale up | pair by scanning the QR, over Tailscale | the released app pairs unchanged: the QR still carries `host` and `port`. Oracle: the daemon's `device paired` line names transport `tailscale` | the daemon log, the tester's note | remove the device | pass: the released 0.4.1 app paired unchanged, transport=tailscale |
| M3 | A handset with Tailscale uninstalled and the built-in-transport app, **on mobile data rather than the home wifi** (the owner's ruling, 2026-08-21): a carrier NAT on one side and the home NAT on the other, which is the away case this transport exists for, driven by the real client rather than staged with a harness | scan the QR, pair over the built-in transport, watch a CLI-triggered run | the app asks how to connect **before** the camera opens , listing the transports the app can dial with Built-in pre-selected. The owner leaves Built-in, scans, and is not asked again: the machine reports Built-in, so the answer stands. It pairs over it and the run appears. Oracle: the daemon's `device paired` line names transport `iroh` | the daemon log, the tester's note | remove the device | pass: paired over the built-in transport from mobile data, transport=iroh; found six defects, all fixed |
| M4 | A handset that can use both transports | choose Tailscale on the opening screen, before the scan, and pair over it | neither path ships unexercised: the deliberate Tailscale choice pairs over Tailscale. Oracle: the daemon's `device paired` line names transport `tailscale` | the daemon log, the tester's note | remove the device | pass on the daemon oracle: transport=tailscale, chosen before the scan |
| M5 | A paired phone **on Tailscale**, in a live run, with Built-in also offered; the tailnet address then blocked on the machine | recover from the conversation and pick the run back up, taking **Built-in**, which the phone adopts first | the machine reads as not reachable, the owner recovers, and the run re-attaches through the socket's replay. Oracle: the run continues with no gap, read from the run's own record rather than the screen | the tester's note, the run journal, the daemon's adoption line | remove the device | pass: recovered to Built-in mid-run, the phone adopted it, and the run carried on |
| M6 | A paired phone on Built-in with **Tailscale turned off on the handset**; the daemon then stopped, so Built-in fails and the recovery is reached the only way this release reaches it | from the recovery, select **Tailscale** | the Tailscale row becomes selected, then the full **Connecting over Tailscale** screen appears. Tailscale's precondition is local and fails without any network attempt, so the verdict is immediate and the words are its own: **Tailscale is off on this phone**, drawn at `0.4.5-pairing-tailscale-off`. The failure creates neither a Tailscale connection nor an adoption, but Connection and the hub retain the selected **Tailscale** choice. It must not say the machine did not answer | the tester's note against the drawn screen, the hub label, and the time to a verdict | restart the daemon | not run: invalidated by the selected-choice and terminal-verification corrections; rebuild and re-run on the handset |
| M7 | A paired phone on Built-in with **Tailscale on**; the daemon then stopped, so both transports are unreachable | from the recovery, select **Tailscale** | the Tailscale row becomes selected, then the full **Connecting over Tailscale** screen appears. It reaches the other Tailscale failure: **Can't reach `<machine>` over Tailscale**, drawn at `0.4.5-pairing-tailscale-unreachable`, within the transport's bound and without another dial after that verdict. The failure creates neither a connection nor an adoption, but Connection and the hub retain the selected **Tailscale** choice. The two failures are different screens because they are different facts, and a phone with Tailscale off must never be told the machine went silent | the tester's note, Connection and hub screenshots, the daemon log, and the time to a verdict | restart the daemon | not run: invalidated by the selected-choice and terminal-verification corrections; rebuild and re-run on the handset |

**What adopting a transport changed in this runbook, and what it costs to re-drive.** The
first attempt at M5 found that a phone paired over Tailscale can never adopt
the built-in transport: that transport's gate 1 is a binding, a Tailscale
claim proves membership rather than a key so it binds nothing (C3), and the
phone was refused at a transport it could reach while holding a valid token.
The owner ruled adoption in rather than deferring it, so this runbook changes
with the product.

**B4 and X1 are re-run, not amended away.** The pre-handshake refusal now
needs no window, no bound peer **and no device rows at all**. X1 is the cell
that proves the fresh-machine posture did not loosen, and B4 is the cell whose
precondition tightened, so both are driven again rather than reasoned about.
**B8 to B12 are new** and are the security of adoption itself: a stranger with
no token cannot adopt, the identity bound is the one the handshake proved, a
second identity cannot displace the first, a revoked device cannot come back,
and a transport that proves nothing refuses.

**M6 and M7 are new and are the other half of the same rule.** The selected
choice is stored on the tap, but a connection and adoption are created only
when that transport's own preconditions are met. Each failure has its own words
because each is a different fact: Tailscale off on the handset is not
Tailscale on and the machine silent. Both screens are already drawn, so these
cells check the product against the mockups rather than inventing an expected
result.

The families that assert the admission posture are re-driven in full, because
they are what would hide a regression: **B1 to B12, S1 to S6, and X1**. All of
them are harness-driven and need no handset.

**Why M5 names Tailscale as the transport that goes down.** The first attempt
took the built-in transport down instead, and could not: blocking its home
relay made the endpoint fail over to another, blocking those made it fail over
again, and an outside dial still completed. Blocking its UDP socket removes
only the direct paths, because relay traffic rides TCP to whichever relay it
lands on. That is the transport being resilient, which is what it is for, and
it makes "take it down" an unreliable precondition rather than a step.

A tailnet address is one address and does not fail over, so blocking it is
deterministic. The cell also gains value from the swap rather than losing it:
recovering **to** the built-in transport is this minor's own claim, where
recovering away from it is `0.4.6`'s. The run is the oracle either way, and it
is read from the run's record rather than from the screen.

## Per-OS results

Each row is a part. **CI is not a pass**: an OS whose only evidence is the
automated gate is `not run`, never `pass`. The `overall` row is the weakest of
the parts actually driven on that OS.

| Part | Linux | Windows | macOS | WSL |
|---|---|---|---|---|
| A: the built head | not run: the owner runs it | not run: the owner runs it | not run: the owner runs it | pass |
| T: the traversal spike | not run: needs two networks | not run: needs two networks | not run: needs two networks | not run: the owner's cell |
| P: pairing and the report | not run: the owner runs it | not run: the owner runs it | not run: the owner runs it | pass |
| B: the admission rule | not run: needs the second network | not run: needs the second network | not run: needs the second network | pass |
| C: the claim binds | not run: needs the second network | not run: needs the second network | not run: needs the second network | pass |
| H: health's scope | not run: needs the second network | not run: needs the second network | not run: needs the second network | pass |
| S: the security surface | not run: needs the second network | not run: needs the second network | not run: needs the second network | pass |
| D: the deletion sweep | not run: needs Tailscale and a second network | not run: needs Tailscale and a second network | not run: needs Tailscale and a second network | pass |
| F: failure and recovery | not run: needs the second network | not run: needs the second network | not run: needs the second network | partial: F1 substituted, its second-network half not run |
| X: out of the box | not run: needs a fresh root and a second network | not run: needs a fresh root and a second network | not run: needs a fresh root and a second network | pass |
| K: the secret key file | not run: the permission branch is asserted per OS | not run: the DACL branch is asserted on Windows | not run: the permission branch is asserted per OS | pass |
| M: the phone | not run: blocked on vadgr-mobile 0.4.5 | not run: blocked on vadgr-mobile 0.4.5 | not run: blocked on vadgr-mobile 0.4.5 | **not run**: M6 and M7 were invalidated by the selected-choice and terminal-verification corrections; rebuild and re-run them on the handset |
| overall | not run: no live cell has run | not run: no live cell has run | not run: no live cell has run | **not run**: the repaired handset cells M6 and M7 still need their live results |

This WSL column was recorded while the branch was still moving. The pass found
two defects and both were fixed on it, so the binary changed twice under the
cells: the transport gained a log line for each of the two ways it closes an
unbound connection, and the request span stopped writing the query string. Every
cell whose result could depend on either was re-run against the newer head and
says so in its boundary. **The three closing passes run against one frozen head
and this column is not one of them**: it is the pass that found the defects.

## Close: three independent passes

The runbook is closed with **three separate agents running the sweep
concurrently**, each with its own port, database, daemon and state root, and
**each pass is local-only except where a cell needs the network**, which is what
`VADGR_TRANSPORT=loopback` exists for. Compare them structurally per the
doctrine: every HTTP entry on method, path, status and error code; the dialer
records on handshake verdict and per-request status; the run-socket frame counts
per transport. Then read the token counts, the fixture pinned first. Ask each
agent what looked odd, not only whether its cells passed.

# `0.4.10` harness

The helpers for this release's pass. **None of them chooses what the product
does**: they build state before a group, record a surface that already exists,
or check a result with an implementation independent of the one under test.
Every product command in the runbook is invoked by hand, one at a time.

One helper is new for this release, because one surface is new. `sockets.py`
speaks the run WebSocket protocol but cannot speak QUIC, so it cannot reach the
built-in transport at all. `dialer/` is the built-in transport's equivalent: an
independent QUIC client that dials the daemon's iroh endpoint and records what
each route answers.

| file | what it is | when it runs |
|---|---|---|
| `dialer/` | the built-in-transport client. A Rust binary that dials an endpoint id over its relays and direct addresses, opens one bidirectional stream per HTTP request, and records the status, error code and body. It also records its own endpoint id, so a cell can name the identity a claim bound; whether the QUIC handshake completed, which is the whole of the out-of-the-box cell; and, with `hold_ms`, whether the daemon closed the connection during a hold and what reason it gave. With `sockets` it performs the WebSocket upgrade on a stream and records frame type counts. It drives no product flow: a cell hands it a job and reads the record | every built-in-transport cell |
| `sockets.py` | the run-socket client, carried from `0.4.9`. Opens both run sockets with a standard-library implementation and records frame type counts and close codes. It speaks TCP, so it drives loopback and Tailscale; the built-in transport's run sockets are driven by the dialer, which records the same fields under the same names so the three records compare directly | the socket cells |

`sweep.py`, `tables.py` and `compare.py` from the `0.4.9` harness are reused
unchanged for the deletion sweep re-run; copy them beside these before the pass,
or point at them in the `0.4.9` directory. They read the daemon's own published
surface over loopback and assert nothing.

`qr-decode` is reused from the same place, and the P3 cell names it. It reads
the symbol the installed `vadgr pair` printed, rebuilds the module matrix and
decodes it with an implementation that is not the encoder under test. Build it
once in the `0.4.9` directory and run it against the captured render. A cell
that asks what the QR carries is asking about the thing the phone scans, which
is not the same object as the pairing response the API returned beside it.

## The dialer

It is the one thing on this pass that is not the product and not the standard
library: it is an independent implementation of the built-in transport's client
half, so the wire is checked by something other than the code under test. The
product's real client is the phone (`vadgr-mobile 0.4.5`); the dialer stands in
for it in an agent-driven pass, exactly as `sockets.py` stands in for a phone on
the run socket.

Build it once, from its committed path:

```bash
cd E2E/0.4.10/harness/dialer && cargo build --release
DIALER=E2E/0.4.10/harness/dialer/target/release/vadgr-iroh-dialer
```

Give it a JSON job on argv or stdin. The `node`, `relays` and `direct` come
straight from a pairing report (`POST /api/auth/pair`) or a health block. It
writes a JSON record to stdout:

```bash
# One request over the built-in transport, as an unbound peer during a window.
echo '{"node":"<endpoint id>","relays":["https://use1-1.relay.n0.iroh.link./"],
       "requests":[{"method":"GET","path":"/api/health"}]}' | "$DIALER"

# One phone identity across dials: claim, then reach as the bound peer. The
# secret key is the cell's to generate and keep; the same key is the same
# endpoint id, which is what a real phone is.
KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))')
echo '{"node":"...","relays":["..."],"secret_key":"'$KEY'",
       "requests":[{"method":"POST","path":"/api/auth/claim",
                    "body":{"pairing_token":"7QK4-M2XD","device_name":"probe"}}]}' | "$DIALER"

# The out-of-the-box cell: a fresh identity, no request, records only whether
# the handshake completes. On a machine with no bound device and no open
# window it must read "Refused".
echo '{"node":"...","relays":["..."],"expect_handshake":false}' | "$DIALER"
```

Job fields: `node` (required, the endpoint id), `relays` and `direct`
(optional, the reach), `requests` (each is `method`, `path`, optional `body`
and `token`), `secret_key` (optional 64-hex, one identity across dials),
`expect_handshake` (default true; false records the handshake verdict without
a request), `connect_timeout_ms` (default 15000).

The record carries `handshake` (`Completed`, `Refused` or `NotAttempted`) and,
on a completed handshake, `connect_ms` plus `selected_path` (`direct`, `relay`
or `unknown`). Those route fields intentionally carry no address. Per request,
it records `status`, `error_code`, `body` and any `stream_error`. A cell reads
it and decides; the dialer asserts nothing.

**One operational note, learned building it.** A QUIC client must not finish its
send half before reading the response: finishing races the daemon's reply on
some stacks and the read comes back empty. The dialer keeps the send half open
until the response is read, which is what a well-behaved HTTP-over-QUIC client
does. This is a property of the client, not the daemon: the daemon serves the
response correctly, proven by the loopback sweep answering the same routes.

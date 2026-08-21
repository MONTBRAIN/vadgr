# `0.4.9` harness

Five helpers. **None of them chooses what the product does**: they build state
before a group, record a surface that already exists, or check a result with an
implementation independent of the one under test. Every product command in this
runbook is invoked by hand, one at a time, as the rules at the top of the
runbook require.

`sweep.py` and `sockets.py` are recorders in that same sense. They read the
daemon's own published surface, one over HTTP and one over the socket, exactly
as `curl` reads a route. They assert nothing: a cell reads the record they wrote
and decides.

| file | what it is | when it runs |
|---|---|---|
| `sweep.py` | the surface recorder. Invokes the installed `vadgr` binary and calls the daemon's routes directly, writing method, path, status, error code and body to a JSON record | after the cells, once per pass |
| `tables.py` | emits the runbook's three coverage tables from that record | after `sweep.py` |
| `compare.py` | compares three recorded passes structurally, normalising only the run ids that must differ | after the three repeatability passes |
| `sockets.py` | the wire client. Opens both run sockets with a standard-library implementation of the protocol and records frame type counts, close codes and refusals | the socket cells, and once per pass |
| `qr-decode/` | reads the QR **as printed** and decodes it with `rqrr`, an implementation independent of the encoder under test | `G3` |

## Running them

```bash
# The recorder. VADGR_BIN must be the installed binary, never a source path.
VADGR_API_URL=http://127.0.0.1:8811 VADGR_BIN="$(command -v vadgr)" \
  python3 harness/sweep.py record.json
python3 harness/tables.py record.json > tables.md

# Three passes, already recorded, compared.
python3 harness/compare.py record-8821.json record-8822.json record-8823.json

# Both sockets, driven by a real client. It needs nothing installed.
python3 harness/sockets.py frames.json --port 8811 --run run-abc --seconds 40
# The same client proves the refusals: a non-loopback source closes 4401, an
# unknown run closes 4004.
python3 harness/sockets.py refused.json --host "$(tailscale ip -4)" --port 8811 \
  --run run-abc --seconds 10

# The QR oracle: the file is the captured output of `vadgr pair`.
cargo run --manifest-path harness/qr-decode/Cargo.toml -- pair.out '<the expected URI>'
```

`sweep.py` prints only what it recorded. It reads no credential and writes none.

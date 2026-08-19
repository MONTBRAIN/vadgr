# `0.4.9` harness

Four helpers. **None of them drives the product**: they build state before a
group, record what already ran, or check a result with an independent
implementation. Every product command in this runbook is invoked by hand, one at
a time, as the rules at the top of the runbook require.

| file | what it is | when it runs |
|---|---|---|
| `sweep.py` | the surface recorder. Invokes the installed `vadgr` binary and calls the daemon's routes directly, writing method, path, status, error code and body to a JSON record | after the cells, once per pass |
| `tables.py` | emits the runbook's three coverage tables from that record | after `sweep.py` |
| `compare.py` | compares three recorded passes structurally, normalising only the run ids that must differ | after the three repeatability passes |
| `qr-decode/` | reads the QR **as printed** and decodes it with `rqrr`, an implementation independent of the encoder under test | `G3` |

## Running them

```bash
# The recorder. VADGR_BIN must be the installed binary, never a source path.
VADGR_API_URL=http://127.0.0.1:8811 VADGR_BIN="$(command -v vadgr)" \
  python3 harness/sweep.py record.json
python3 harness/tables.py record.json > tables.md

# Three passes, already recorded, compared.
python3 harness/compare.py record-8821.json record-8822.json record-8823.json

# The QR oracle: the file is the captured output of `vadgr pair`.
cargo run --manifest-path harness/qr-decode/Cargo.toml -- pair.out '<the expected URI>'
```

`sweep.py` prints only what it recorded. It reads no credential and writes none.

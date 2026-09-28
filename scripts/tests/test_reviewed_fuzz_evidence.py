"""The numerical malformed-fixture interpretation never becomes a generic exemption."""

import hashlib
import zlib

import pytest

from scripts import reviewed_fuzz_evidence as fuzz


@pytest.mark.parametrize("digest", fuzz.REVIEWED)
def test_exact_fixture_bit_interpretation_is_not_a_decompression_claim(digest):
    raw = bytes.fromhex(fuzz.REVIEWED[digest]["hex"])
    assert hashlib.sha256(raw).hexdigest() == digest
    with pytest.raises(zlib.error, match="missing end-of-block"):
        zlib.decompress(raw)
    result = fuzz.inspect_fuzz(raw)
    assert result["valid_compressed_document"] is False
    assert result["literal_length_widths"][256] == 0
    assert result["suffix_start_bit"] == fuzz.REVIEWED[digest]["table_end_bit"]
    assert result["status"] == "complete-reviewed-binary-record-no-ownership-statement"
    for index in range(len(raw) * 8):
        changed = bytearray(raw)
        changed[index // 8] ^= 1 << (index % 8)
        with pytest.raises(ValueError, match="identity differs"):
            fuzz.inspect_fuzz(changed)
    for value in (raw[:-1], raw + b"Copyright Another Owner", zlib.compress(b"Copyright Actual Owner")):
        with pytest.raises(ValueError, match="identity differs"):
            fuzz.inspect_fuzz(value)


def test_canonical_huffman_codes_follow_numeric_symbol_order():
    assert fuzz.canonical_codes([3, 3, 3, 3, 3, 2, 4, 4]) == {
        (2, 0): 5, (3, 2): 0, (3, 3): 1, (3, 4): 2,
        (3, 5): 3, (3, 6): 4, (4, 14): 6, (4, 15): 7,
    }
    with pytest.raises(ValueError, match="oversubscribed"):
        fuzz.canonical_codes([1, 1, 1])


def test_numerical_suffix_interpretation_must_cover_the_entire_record(monkeypatch):
    digest, record = next(iter(fuzz.REVIEWED.items()))
    raw = bytes.fromhex(record["hex"])
    monkeypatch.setitem(fuzz.REVIEWED, digest, {**record, "suffix_runs": record["suffix_runs"][:-1]})
    with pytest.raises(ValueError, match="incomplete"):
        fuzz.inspect_fuzz(raw)

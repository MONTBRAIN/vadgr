"""Bit-level inspection of two exact malformed numerical DEFLATE test vectors.

These are deliberately invalid inputs, not successfully decompressed documents.
Only the two complete reviewed byte sequences qualify. Decoder rejection alone
never establishes absence, and a changed suffix loses this interpretation.
"""

import hashlib


REVIEWED = {
    "9eafada86c8d8af16b90b280e77fd4aa750fa8fb54e31623dc3aaac8097d0c2f": {
        "hex": "5809ecc8210a00000010b8010100001a007f7a07ff7f0000008104000030005b020000ffffff00c2c2",
        "final": 0, "distance_count": 9, "code_length_count": 18, "table_end_bit": 254,
        "suffix_runs": [[1, 1], [0, 2], [1, 1], [0, 22], [1, 24], [0, 9], [1, 1],
                        [0, 4], [1, 2], [0, 1], [1, 1], [0, 4], [1, 2]],
    },
    "bf63f178c0c288e004339e2d3084adce4c43064697b860accf13bb81fa5fa1f2": {
        "hex": "5809ed40c8210a8f0004c5c5c50000000000000000000000180000000000000000000000000000030001000000000000ffffffff",
        "final": 1, "distance_count": 1, "code_length_count": 6, "table_end_bit": 349,
        "suffix_runs": [[0, 35], [1, 32]],
    },
}


def canonical_codes(lengths):
    counts = [lengths.count(width) for width in range(16)]
    code, table = 0, {}
    for width in range(1, 16):
        code = (code + (counts[width - 1] if width > 1 else 0)) << 1
        if code + counts[width] > 1 << width:
            raise ValueError("oversubscribed reviewed Huffman table")
        for symbol, size in enumerate(lengths):
            if size == width:
                table[width, code] = symbol
                code += 1
        code -= counts[width]
    return table


def inspect_fuzz(raw):
    expected = REVIEWED.get(hashlib.sha256(raw).hexdigest())
    if expected is None or raw.hex() != expected["hex"]:
        raise ValueError("reviewed malformed fixture identity differs")
    position, fields = 0, []

    def take(count, meaning):
        nonlocal position
        if count <= 0 or position + count > len(raw) * 8:
            raise ValueError("reviewed bit range exceeds fixture")
        start = position
        bits = [(raw[index // 8] >> (index % 8)) & 1 for index in range(start, start + count)]
        position += count
        value = sum(bit << index for index, bit in enumerate(bits))
        fields.append({"bit_offset": start, "end_bit_exclusive": position,
                       "transmission_bits": "".join(map(str, bits)), "value_lsb_first": value,
                       "interpretation": meaning})
        return value

    def symbol(table):
        code = 0
        for width in range(1, 16):
            code = (code << 1) | take(1, "Code-length alphabet Huffman bit, most-significant code bit first")
            if (width, code) in table:
                return table[width, code]
        raise ValueError("unknown reviewed Huffman code")

    cmf = take(8, "Zlib CMF: DEFLATE method 8, window-size exponent 5")
    flg = take(8, "Zlib FLG: no preset dictionary, level zero, header check bits")
    if cmf != 0x58 or flg != 9 or ((cmf << 8) | flg) % 31:
        raise ValueError("reviewed zlib header differs")
    final = take(1, "BFINAL flag")
    block_type = take(2, "BTYPE: dynamic Huffman block")
    literal_count = take(5, "HLIT minus 257") + 257
    distance_count = take(5, "HDIST minus 1") + 1
    code_count = take(4, "HCLEN minus 4") + 4
    if (final, block_type, literal_count, distance_count, code_count) != (
            expected["final"], 2, 286, expected["distance_count"], expected["code_length_count"]):
        raise ValueError("reviewed dynamic header differs")
    lengths = [0] * 19
    for value in (16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15)[:code_count]:
        lengths[value] = take(3, f"Huffman width for code-length alphabet symbol {value}")
    table, decoded, instructions = canonical_codes(lengths), [], []
    while len(decoded) < literal_count + distance_count:
        start, before = position, len(decoded)
        code = symbol(table)
        if code < 16:
            values = [code]
        elif code == 16:
            if not decoded:
                raise ValueError("repeat has no preceding length")
            values = [decoded[-1]] * (3 + take(2, "Previous code length repetition count minus 3"))
        elif code == 17:
            values = [0] * (3 + take(3, "Zero code length repetition count minus 3"))
        else:
            values = [0] * (11 + take(7, "Zero code length repetition count minus 11"))
        decoded.extend(values)
        instructions.append({"bit_offset": start, "end_bit_exclusive": position,
                             "symbol": code, "first_index": before, "count": len(values), "length": values[0]})
    if (len(decoded) != literal_count + distance_count or decoded[256] != 0
            or position != expected["table_end_bit"]):
        raise ValueError("reviewed malformed code table differs")
    suffix_start = position
    for bit, count in expected["suffix_runs"]:
        value = take(count, f"Exact inspected numerical fuzz suffix: {count} repeated {bit} bits")
        if value != ((1 << count) - 1 if bit else 0):
            raise ValueError("reviewed numerical suffix differs")
    if position != len(raw) * 8:
        raise ValueError("incomplete reviewed malformed fixture coverage")
    return {"status": "complete-reviewed-binary-record-no-ownership-statement",
        "format": "Exact malformed dynamic-Huffman numerical regression vector",
        "format_references": ["https://www.rfc-editor.org/rfc/rfc1950#section-2.2",
                              "https://www.rfc-editor.org/rfc/rfc1951#section-3.2.7"],
        "complete_input_hex": raw.hex(), "reviewed_bit_ranges": fields,
        "code_length_alphabet": lengths, "code_length_instructions": instructions,
        "literal_length_widths": decoded[:literal_count], "distance_widths": decoded[literal_count:],
        "missing_end_of_block_symbol": 256, "suffix_start_bit": suffix_start,
        "suffix_runs": expected["suffix_runs"], "valid_compressed_document": False,
        "meaning": "Every bit of these exact small test vectors is inspected: zlib and dynamic-block fields, numerical code-table instructions, and the complete listed corrupt suffix. Neither table assigns an end-of-block code. The suffix is retained as numerical fuzz input, not silently discarded or described as plaintext or a validated checksum. There is no ownership statement in this complete inspected record. This exact-byte finding does not infer anything about another malformed stream, its author or its license."}

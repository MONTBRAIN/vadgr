"""Complete typed decoding of exact reviewed certificate test fixtures.

This is not a generic DER exemption. Certificate identity names are not inferred
to be copyright owners. Unknown bytes or a different certificate remain open.
"""

import hashlib


REVIEWED = {
    "bf32da954571659aaf715c13ee703e3643dfcbaeee2d82110ca68eb57cb67ce0": 1654,
    "46edc3689046d53a453fb3104ab80dcaec658b2660ea1629dd7e867990648716": 1127,
    "8f0d491077ddc360e7416620af2cf4a8a4010e5b6f5a6d0f557f4f2499a38029": 1649,
    "e77868335868ec346608b1a2953ac0a892eb3f6fc7040336fa62db63c7b8c2d9": 526,
    "86d218374763fce77d5b2b45398db48f10e553da1875be7d6103085baca0343f": 896,
    "967ed7ed2be0506b82000a377751c5525619d3b9e7fed8a0e7aa554947af5e9e": 893,
    "e1eee9ac618291e899456ebc23edb63a9bf732d57c93864f940da142ad05e54d": 1436,
    "aa9ca48b01eba9c03f2c221ff19fb0c29228d5c03a41204411a5367bd305a16f": 933,
}


def inspect_certificate(raw, markers):
    expected = REVIEWED.get(hashlib.sha256(raw).hexdigest())
    if expected is None or len(raw) != expected:
        raise ValueError("reviewed certificate identity differs")
    fields = []

    def retain(start, end, meaning, text=None):
        row = {"offset": start, "end_exclusive": end, "interpretation": meaning, "hex": raw[start:end].hex()}
        if text is not None:
            if markers.search(text):
                raise ValueError("ambiguous ownership marker in certificate field")
            row["decoded_text"] = text
        fields.append(row)

    def sequence(start, end, extension=None, inner_octet=False):
        previous_oid = None
        while start < end:
            position = start
            tag, length = raw[start], raw[start + 1]
            start += 2
            if tag & 31 == 31 or length == 128:
                raise ValueError("unreviewed certificate encoding")
            if length & 128:
                count = length & 127
                if not 1 <= count <= 3 or start + count > end or raw[start] == 0:
                    raise ValueError("invalid certificate length")
                length = int.from_bytes(raw[start:start + count], "big")
                start += count
            stop = start + length
            if stop > end:
                raise ValueError("certificate field exceeds container")
            retain(position, start, f"DER tag 0x{tag:02x} and definite length {length}")
            value = raw[start:stop]
            if tag & 32:
                sequence(start, stop, extension)
            elif tag in (12, 19, 22, 23, 24, 30, 134, 130):
                codec = "utf-8" if tag == 12 else "utf-16-be" if tag == 30 else "ascii"
                retain(start, stop, "Certificate name, validity time, DNS name, URI or policy text", value.decode(codec))
            elif tag == 6:
                numbers, number = [], 0
                for byte in value:
                    number = (number << 7) | (byte & 127)
                    if not byte & 128:
                        numbers.append(number)
                        number = 0
                if not numbers or value[-1] & 128:
                    raise ValueError("invalid certificate object identifier")
                first = min(numbers[0] // 40, 2)
                previous_oid = ".".join(map(str, (first, numbers[0] - first * 40, *numbers[1:])))
                retain(start, stop, "ASN.1 object identifier " + previous_oid)
            elif tag == 4:
                selected = previous_oid or extension
                if selected == "2.5.29.14" and inner_octet and length == 20:
                    retain(start, stop, "Subject public-key identifier: 20 hash bytes")
                elif selected in {"2.5.29.35", "2.5.29.14", "2.5.29.15", "2.5.29.32", "2.5.29.19",
                                  "2.5.29.31", "1.3.6.1.5.5.7.1.1", "2.5.29.37", "2.5.29.17"}:
                    sequence(start, stop, selected, True)
                else:
                    raise ValueError("unreviewed certificate octet string")
            elif tag == 128 and extension == "2.5.29.35" and length == 20:
                retain(start, stop, "Authority public-key identifier: 20 hash bytes")
            elif tag == 3:
                if not value or value[0] > 7:
                    raise ValueError("invalid certificate bit string")
                if value[0] == 0 and value[1:2] == b"\x30" and length in (271, 527):
                    retain(start, start + 1, "RSA public-key bit string: zero unused bits")
                    sequence(start + 1, stop)
                elif expected == 526 and value[0] == 0 and value[1:2] == b"\x30" and length == 104:
                    retain(start, start + 1, "ECDSA signature bit string: zero unused bits")
                    sequence(start + 1, stop)
                elif expected == 526 and length == 98 and value[:2] == b"\0\4":
                    retain(start, start + 1, "Elliptic-curve public-key bit string: zero unused bits")
                    retain(start + 1, start + 2, "Uncompressed elliptic-curve point format")
                    retain(start + 2, start + 50, "384-bit mathematical public x coordinate")
                    retain(start + 50, stop, "384-bit mathematical public y coordinate")
                elif length in (257, 513) and value[0] == 0:
                    retain(start, stop, "RSA certificate signature: unused-bit count and mathematical signature value")
                elif extension == "2.5.29.15" and length == 2:
                    retain(start, stop, "Key-usage flags and unused-bit count")
                else:
                    raise ValueError("unreviewed certificate bit string")
            elif tag == 2:
                retain(start, stop, "ASN.1 integer: version, serial number, path constraint, RSA parameter or ECDSA signature parameter")
            elif tag == 1 and value in (b"\x00", b"\xff"):
                retain(start, stop, "ASN.1 boolean")
            elif tag == 5 and not value:
                pass
            else:
                raise ValueError(f"unreviewed certificate field 0x{tag:02x}")
            start = stop
        if start != end:
            raise ValueError("uninspected certificate trailer")

    sequence(0, len(raw))
    if (fields[0]["offset"] != 0 or fields[-1]["end_exclusive"] != len(raw)
            or any(left["end_exclusive"] != right["offset"] for left, right in zip(fields, fields[1:]))):
        raise ValueError("incomplete certificate byte coverage")
    request = hashlib.sha256(raw).hexdigest() == "aa9ca48b01eba9c03f2c221ff19fb0c29228d5c03a41204411a5367bd305a16f"
    return {"status": "complete-reviewed-binary-record-no-ownership-statement",
        "format": "Exact PKCS#10 DER certificate request with fully decoded fields" if request
                  else "Exact X.509 DER test certificate with fully decoded fields",
        "reviewed_byte_ranges": fields,
        "meaning": "Every byte belongs to an inspected typed field. Certificate subject and issuer names are identities, not copyright declarations. All policy text is decoded. No trust or package approval is granted."}

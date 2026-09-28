"""Typed source evidence for exact CMS fixtures, without decrypting unknown content."""

import hashlib
import zlib


PREFIX = "cms-0.2.3/tests/"
REVIEWED = {
    "compressed_data.bin": ("66279624e806691ca3cd920d357ec1d11141b75cf0372c650294472fb3560d7e",
                            "abedd3a2b717abeb696acb1c76dd939c4094e861c46b2a59db68643ad2835749"),
    "digested_data.bin": ("dde579b1b0939c31bba984f67b03dcd1f49764d0aea5751a1a451ecbb9265171",
                          "84b7b6b74bedba137579bee5358c648cb70cf9e23d705212fabea7b73a836854"),
    "encrypted_data.bin": ("acf76585010e3f8fb7a7a1709c1d9eec2b3345088dabdfba9dd84022e81ac2dd",
                           "22b657b794a10292acc0f5a9211fe6d041573cd77724c269913716192766e48e"),
}
DATA_SHA256 = "56293a80e0394d252e995f2debccea8223e4b5b2b150bee212729b3b39ac4d46"
KEYS = {
    "rsa2048-priv.der": "f94b60300e4877e863b2bea8d5c366a90432794454c05e0ec098ddbf96263614",
    "p256-priv.der": "8125ab208d2181ed3ef05ff0ab1906e5898c36a858277e5b987e78e505288769",
}
KEY_CONTEXT_SHA256 = "75e40cf53b42d81628149ba2425336ae3f2c95470bf79f6b9187a825f598aaaf"
OIDS = {
    "2a864886f70d0109100109": "CMS compressedData 1.2.840.113549.1.9.16.1.9",
    "2a864886f70d0109100308": "Zlib compression 1.2.840.113549.1.9.16.3.8",
    "2a864886f70d010705": "CMS digestedData 1.2.840.113549.1.7.5",
    "2a864886f70d010706": "CMS encryptedData 1.2.840.113549.1.7.6",
    "2a864886f70d010701": "CMS data 1.2.840.113549.1.7.1",
    "2b0e03021a": "SHA-1 digest 1.3.14.3.2.26",
    "608648016503040102": "AES-128-CBC 2.16.840.1.101.3.4.1.2",
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def inspect_key(name, raw):
    if digest(raw) != KEYS.get(name):
        raise ValueError("reviewed CMS key identity differs")
    # Exact DER boundaries were independently read with a PKCS#1/PKCS#8 decoder.
    # These public test keys carry numerical parameters, not identity attributes.
    if name == "rsa2048-priv.der":
        parts = [(0, 4, "PKCS#1 sequence header"), (4, 6, "Version INTEGER header"), (6, 7, "Version zero")]
        boundaries = ((7, 11, 268), (268, 270, 273), (273, 277, 533), (533, 536, 665),
                      (665, 668, 797), (797, 800, 929), (929, 932, 1060), (1060, 1063, 1191))
        names = ("modulus", "public exponent", "private exponent", "prime one", "prime two",
                 "exponent one", "exponent two", "CRT coefficient")
        values = []
        for (start, data, end), label in zip(boundaries, names):
            parts.extend(((start, data, "DER INTEGER header: " + label),
                          (data, end, "RSA mathematical parameter: " + label)))
            values.append(int.from_bytes(raw[data:end], "big"))
        modulus, public, private, first, second, dp, dq, coefficient = values
        if (first * second != modulus or public != 65537 or modulus.bit_length() != 2048
                or dp != private % (first - 1) or dq != private % (second - 1)
                or coefficient * second % first != 1
                or public * private % ((first - 1) * (second - 1)) != 1):
            raise ValueError("reviewed RSA numerical relationships differ")
    else:
        parts = [(0, 3, "PKCS#8 sequence header"), (3, 5, "Version INTEGER header"), (5, 6, "Version zero"),
            (6, 8, "AlgorithmIdentifier sequence header"), (8, 10, "Algorithm OBJECT IDENTIFIER header"),
            (10, 17, "EC public key algorithm 1.2.840.10045.2.1"), (17, 19, "Curve OBJECT IDENTIFIER header"),
            (19, 27, "NIST P-256 curve 1.2.840.10045.3.1.7"), (27, 29, "Private-key OCTET STRING header"),
            (29, 31, "Nested SEC1 sequence header"), (31, 33, "SEC1 version INTEGER header"),
            (33, 34, "SEC1 version one"), (34, 36, "Private scalar OCTET STRING header"),
            (36, 68, "256-bit mathematical private scalar"), (68, 70, "Public-key explicit context 1 header"),
            (70, 72, "Public-key BIT STRING header"), (72, 73, "Zero unused bits"),
            (73, 74, "Uncompressed elliptic-curve point format"), (74, 106, "256-bit public x coordinate"),
            (106, 138, "256-bit public y coordinate")]
        prime = 0xffffffff00000001000000000000000000000000ffffffffffffffffffffffff
        b = 0x5ac635d8aa3a93e7b3ebbd55769886bc651d06b0cc53b0f63bce3c3e27d2604b
        x, y = int.from_bytes(raw[74:106], "big"), int.from_bytes(raw[106:138], "big")
        if raw[72:74] != b"\0\4" or not (x < prime and y < prime) or (y*y - x*x*x + 3*x - b) % prime:
            raise ValueError("reviewed EC numerical relationships differ")
    if parts[0][0] != 0 or parts[-1][1] != len(raw) or any(a[1] != b[0] for a, b in zip(parts, parts[1:])):
        raise ValueError("incomplete reviewed key coverage")
    return {"status": "complete-reviewed-binary-record-no-ownership-statement",
        "format": "Exact public CMS regression-test private-key DER fixture",
        "reviewed_byte_ranges": [{"offset": start, "end_exclusive": end, "interpretation": meaning,
                                  "hex": raw[start:end].hex()} for start, end, meaning in parts],
        "meaning": "Every byte is an inspected key-format field or mathematical parameter. No attribute bag, identity, text, comment or trailer exists. This public test key must never be used as a production credential; no ownership or trust is inferred."}


def inspect_cms(name, raw, plaintext, markers):
    if name not in REVIEWED or digest(raw) != REVIEWED[name][0] or digest(plaintext) != DATA_SHA256:
        raise ValueError("reviewed CMS fixture identity differs")
    text = plaintext.decode("utf-8")
    if markers.search(text):
        raise ValueError("ownership marker in CMS plaintext")
    fields, content = [], {}

    def retain(start, end, meaning, **values):
        fields.append({"offset": start, "end_exclusive": end, "hex": raw[start:end].hex(),
                       "interpretation": meaning, **values})

    def parse(start, end):
        while start < end:
            header = start
            if start + 2 > end:
                raise ValueError("truncated CMS header")
            tag, length = raw[start:start + 2]
            start += 2
            if tag & 31 == 31 or length == 128:
                raise ValueError("unreviewed CMS encoding")
            if length & 128:
                count = length & 127
                if count > 2 or start + count > end or raw[start] == 0:
                    raise ValueError("invalid CMS length")
                length = int.from_bytes(raw[start:start + count], "big")
                start += count
                if length < 128:
                    raise ValueError("nonminimal CMS length")
            stop = start + length
            if stop > end:
                raise ValueError("CMS value exceeds its container")
            retain(header, start, f"DER tag 0x{tag:02x} and definite length {length}")
            value = raw[start:stop]
            if tag in (0x30, 0xA0):
                parse(start, stop)
            elif tag == 6 and value.hex() in OIDS:
                retain(start, stop, "Object identifier: " + OIDS[value.hex()])
            elif tag == 2 and value == b"\0":
                retain(start, stop, "CMS version zero")
            elif name == "compressed_data.bin" and tag == 4 and start == 66:
                decoder = zlib.decompressobj()
                decoded = decoder.decompress(value, 1024)
                if (not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or decoded != plaintext):
                    raise ValueError("CMS compressed plaintext differs")
                retain(start, stop, "Complete zlib stream, including validated checksum, equals the exact data.txt",
                       decoded_text=text, decoded_sha256=DATA_SHA256, decoded_size=len(decoded))
                content["plaintext_verified"] = True
            elif name == "digested_data.bin" and tag == 4 and start == 58 and value == plaintext:
                retain(start, stop, "Encapsulated data equals the exact data.txt", decoded_text=text)
                content["plaintext_verified"] = True
            elif name == "digested_data.bin" and tag == 4 and start == 506:
                if value != hashlib.sha1(plaintext).digest():
                    raise ValueError("CMS sample digest differs")
                retain(start, stop, "SHA-1 sample-content checksum, independently recomputed; not a security approval")
            elif name == "encrypted_data.bin" and tag == 4 and start == 56:
                if value.hex() != "898082d894ea58bbfbb46d4626edc2bc":
                    raise ValueError("CMS initialization vector differs")
                retain(start, stop, "AES-128-CBC initialization vector, matching the exact source assertion")
            elif name == "encrypted_data.bin" and tag == 0x80 and start == 76 and length == 448:
                retain(start, stop, "Encrypted content: bytes accounted for, plaintext and ownership content unresolved",
                       status="opaque-encrypted-content", sha256=digest(value))
                content["unresolved_encrypted_content"] = {"offset": start, "size": length, "sha256": digest(value)}
            else:
                raise ValueError("unreviewed CMS field")
            start = stop

    parse(0, len(raw))
    if (not fields or fields[0]["offset"] != 0 or fields[-1]["end_exclusive"] != len(raw)
            or any(left["end_exclusive"] != right["offset"] for left, right in zip(fields, fields[1:]))):
        raise ValueError("incomplete CMS byte coverage")
    complete = content.get("plaintext_verified", False)
    if complete == (name == "encrypted_data.bin"):
        raise ValueError("CMS content classification differs")
    return {"status": "complete-reviewed-binary-record-no-ownership-statement" if complete else "undecoded-member-needs-review",
        "format": "Exact CMS " + name.removesuffix(".bin") + " DER fixture",
        "reviewed_byte_ranges": fields, **content,
        "source_plaintext": {"path": PREFIX + "examples/data.txt", "sha256": DATA_SHA256,
                             "binding": "exact-decoded-equality" if complete else "not-established"},
        "meaning": ("Every typed field is inspected. All message content equals the retained sample text, which contains no ownership statement. No author or owner is inferred."
                    if complete else "Only the envelope and encryption parameters are decoded. The source test re-encodes ciphertext and supplies no decryption key. Its copied comment names digested_data.bin, not this encrypted input. No plaintext match or copyright absence is inferred."),
        "format_references": ["https://www.rfc-editor.org/rfc/rfc5652#section-7",
                              "https://www.rfc-editor.org/rfc/rfc5652#section-8",
                              "https://www.rfc-editor.org/rfc/rfc3274"]}


def inspect_cms_fixtures(files, retained, markers):
    plaintext = retained[PREFIX + "examples/data.txt"]
    for row in files:
        name = row["path"].removeprefix(PREFIX + "examples/")
        if name in KEYS:
            test = PREFIX + "builder.rs"
            if digest(retained[test]) != KEY_CONTEXT_SHA256:
                raise ValueError("CMS key source context differs")
            row.update(inspect_key(name, retained[row["path"]]))
            row["fixture_source_context"] = {test: KEY_CONTEXT_SHA256}
            continue
        if name not in REVIEWED:
            continue
        test = PREFIX + name.removesuffix(".bin") + ".rs"
        if digest(retained[test]) != REVIEWED[name][1]:
            raise ValueError("CMS fixture source context differs")
        row.update(inspect_cms(name, retained[row["path"]], plaintext, markers))
        row["fixture_source_context"] = {test: REVIEWED[name][1]}

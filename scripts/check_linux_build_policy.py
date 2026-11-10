#!/usr/bin/env python3
"""Read the mandatory Linux ELF classification note without executing payloads."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import selectors
import stat
import struct
import subprocess
import time

MAX_BINARY = 256 * 1024 * 1024
NOTE_TYPE = 0x56444752
OWNER = b"VADGR\0"
MACHINES = {"x86_64": 62, "aarch64": 183}
MODES = {1: "release", 2: "development"}


class PolicyError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise PolicyError(message)


def span(data, offset, size):
    require(0 <= offset <= len(data) and 0 <= size <= len(data) - offset,
            "ELF range is invalid")
    return data[offset:offset + size]


def header(data, architecture):
    require(architecture in MACHINES and 64 <= len(data) <= MAX_BINARY,
            "ELF size or architecture is invalid")
    require(data[:7] == b"\x7fELF\x02\x01\x01", "64-bit little-endian ELF required")
    row = struct.unpack("<16sHHIQQQIHHHHHH", data[:64])
    require(row[1] in (2, 3) and row[2] == MACHINES[architecture]
            and row[3] == 1 and row[8] == 64, "ELF identity differs")
    return row


def inspect_binary(data, architecture):
    row = header(data, architecture)
    offset, entry_size, count = row[5], row[9], row[10]
    require(entry_size == 56 and 0 < count <= 1024, "ELF program table is invalid")
    table = span(data, offset, count * entry_size)
    found = []
    seen_ranges = []
    for index in range(count):
        segment = struct.unpack_from("<IIQQQQQQ", table, index * entry_size)
        if segment[0] != 4:
            continue
        start, size = segment[2], segment[5]
        require(size <= 1024 * 1024 and all(start + size <= a or start >= b
                for a,b in seen_ranges), "ELF note segments overlap or exceed bounds")
        seen_ranges.append((start, start + size))
        notes = span(data, start, size)
        cursor = 0
        while cursor < len(notes):
            require(len(notes) - cursor >= 12, "truncated ELF note")
            name_size, desc_size, kind = struct.unpack_from("<III", notes, cursor)
            require(name_size <= 256 and desc_size <= 65536, "ELF note exceeds bounds")
            cursor += 12
            name = span(notes, cursor, name_size)
            cursor += (name_size + 3) & ~3
            desc = span(notes, cursor, desc_size)
            cursor += (desc_size + 3) & ~3
            require(cursor <= len(notes), "truncated ELF note padding")
            if kind == NOTE_TYPE or name.rstrip(b"\0") == OWNER.rstrip(b"\0"):
                require(kind == NOTE_TYPE and name == OWNER and len(desc) == 8,
                        "malformed Vadgr build policy note")
                schema, mode = struct.unpack("<II", desc)
                require(schema == 1 and mode in MODES, "unknown Vadgr build policy")
                found.append(MODES[mode])
    require(len(found) == 1, "exactly one Vadgr build policy note required")
    return {"schema": 1, "mode": found[0], "architecture": architecture}


def regular(path, maximum, *, allow_hardlinks=False):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and (allow_hardlinks or info.st_nlink == 1)
            and 0 < info.st_size <= maximum, "unsafe or oversized policy subject")


def expected(result, mode):
    require(mode in MODES.values() and result["mode"] == mode, "Linux build mode differs")
    return result


def verify(binary, mode, architecture):
    # Cargo hard-links the final executable to its dependency output. This
    # read-only classification checks those same bytes, not an immutable receipt.
    regular(binary, MAX_BINARY, allow_hardlinks=True)
    return expected(inspect_binary(binary.read_bytes(), architecture), mode)


def normalized_runtime(data, architecture):
    """Only appimagetool's fixed MD5 metadata slot may differ from the runtime pin."""
    row = header(data, architecture)
    offset, entry_size, count, names_index = row[6], row[11], row[12], row[13]
    require(entry_size == 64 and 0 < names_index < count <= 1024,
            "AppImage section table differs")
    table = span(data, offset, count * entry_size)
    sections = [struct.unpack_from("<IIQQQQIIQQ", table, index * entry_size) for index in range(count)]
    names_row = sections[names_index]
    require(names_row[1] == 3, "AppImage section names differ")
    names = span(data, names_row[4], names_row[5])
    matches = []
    for section in sections:
        require(section[0] < len(names), "AppImage section name is invalid")
        end = names.find(b"\0", section[0])
        require(end >= 0, "unterminated AppImage section name")
        if names[section[0]:end] == b".digest_md5":
            require(section[1] == 1 and section[5] == 16, "AppImage digest slot differs")
            span(data, section[4], 16)
            matches.append(section[4])
    require(len(matches) == 1, "unique AppImage digest slot required")
    output = bytearray(data)
    output[matches[0]:matches[0] + 16] = bytes(16)
    return bytes(output)


def extract_executable(image, offset):
    """A trusted host decoder reads bounded bytes; the AppImage is never executed."""
    command = ["unsquashfs", "-o", str(offset), "-cat", str(image), "usr/bin/vadgr"]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
        output = bytearray()
        deadline = time.monotonic() + 60
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    require(remaining > 0 and selector.select(remaining), "AppImage decoder timed out")
                    block = os.read(process.stdout.fileno(), 1024 * 1024)
                    if not block:
                        break
                    output.extend(block)
                    require(len(output) <= MAX_BINARY, "AppImage executable exceeds bounds")
            require(process.wait(timeout=max(0.01, deadline - time.monotonic())) == 0,
                    "AppImage executable could not be read")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    return bytes(output)


def verify_appimage(image, mode, architecture, pins):
    regular(image, 2 * 1024 * 1024 * 1024)
    row = json.loads(pins.read_bytes())["targets"][architecture]
    require(type(row["size"]) is int and 0 < row["size"] <= 16 * 1024 * 1024,
            "AppImage runtime size pin is invalid")
    with image.open("rb") as stream:
        runtime = stream.read(row["size"])
        require(stream.read(4) == b"hsqs", "pinned AppImage filesystem offset differs")
    require(hashlib.sha256(normalized_runtime(runtime, architecture)).hexdigest() == row["sha256"],
            "AppImage runtime pin differs")
    return expected(inspect_binary(extract_executable(image, row["size"]), architecture), mode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subjects = parser.add_mutually_exclusive_group(required=True)
    subjects.add_argument("--binary", type=Path)
    subjects.add_argument("--appimage", type=Path)
    parser.add_argument("--expect", choices=MODES.values(), required=True)
    parser.add_argument("--architecture", choices=MACHINES, required=True)
    parser.add_argument("--runtime-pins", type=Path,
                        default=Path(__file__).resolve().parents[1] / "packaging/linux/runtime.json")
    args = parser.parse_args()
    try:
        result = (verify(args.binary, args.expect, args.architecture) if args.binary else
                  verify_appimage(args.appimage, args.expect, args.architecture, args.runtime_pins))
    except (PolicyError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Linux build policy refused: {error}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

"""Bridge protocol: length-prefixed JSON over TCP."""

import json
import os
import struct
import uuid
from typing import Any

DEFAULT_PORT = 19542
ENV_PORT_KEY = "CUE_BRIDGE_PORT"
HEADER_SIZE = 4  # 4-byte big-endian uint32


def get_port() -> int:
    return int(os.environ.get(ENV_PORT_KEY, str(DEFAULT_PORT)))


def encode_message(msg: dict) -> bytes:
    payload = json.dumps(msg, separators=(",", ":")).encode("utf-8")
    return struct.pack("!I", len(payload)) + payload


def decode_header(data: bytes) -> int:
    return struct.unpack("!I", data)[0]


def make_request(method: str, params: dict | None = None) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "method": method,
        "params": params or {},
    }


def make_response(request_id: str, result: Any = None) -> dict:
    return {"id": request_id, "ok": True, "result": result or {}}


def make_error(request_id: str, error: str) -> dict:
    return {"id": request_id, "ok": False, "error": error}

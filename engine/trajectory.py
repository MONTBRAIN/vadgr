"""The append-only JSONL resume journal (and find-latest-and-continue resume).

One monotonic ``seq``, code-enforced by the loop, secret-redacted on write. It
is the durable record a resume reads -- not the LLM transcript. Every tool call
writes ``in_flight`` before dispatch and ``done``/``error`` after; a crash
between them leaves a dangling ``in_flight`` line, the exact signal resume keys
on. Full durable execution (snapshots, cross-process recovery, the enforced
idempotency contract) is a later minor -- this slice ships the journal + a
tail-read resume.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Keys whose values are secrets regardless of content.
_SECRET_KEY = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|authorization|bearer|"
    r"credential|client[_-]?secret|access[_-]?token|refresh[_-]?token)",
    re.IGNORECASE,
)
# Values that look like credentials regardless of their key.
_SECRET_VALUE = re.compile(r"(sk-[A-Za-z0-9-]{8,}|Bearer\s+[A-Za-z0-9._-]{8,})")

_REDACTED = "[REDACTED]"


def redact_secrets(payload: Any) -> Any:
    """Deep-copy ``payload`` with tokens/keys stripped. Applied by ``Trajectory``
    on every write, so no credential ever reaches disk."""
    if isinstance(payload, dict):
        out: dict = {}
        for key, value in payload.items():
            if isinstance(key, str) and _SECRET_KEY.search(key):
                out[key] = _REDACTED
            else:
                out[key] = redact_secrets(value)
        return out
    if isinstance(payload, list):
        return [redact_secrets(v) for v in payload]
    if isinstance(payload, str):
        return _SECRET_VALUE.sub(_REDACTED, payload)
    return payload


def _idem(tool: str, params: dict) -> str:
    canonical = json.dumps({"tool": tool, "params": params}, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def _default_runs_dir() -> Path:
    return Path.home() / ".vadgr" / "runs"


class Trajectory:
    """Append-only JSONL resume journal. Single monotonic ``seq``; every tool
    call writes ``in_flight`` before dispatch and ``done``/``error`` after.
    Secrets redacted on write. Path: ``~/.vadgr/runs/<run_id>/trajectory.jsonl``."""

    def __init__(self, run_id: str, path: str | None = None):
        self.run_id = run_id
        if path is None:
            path = str(_default_runs_dir() / run_id / "trajectory.jsonl")
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._seq = -1

    def _write(self, record: dict) -> None:
        record = {"ts": datetime.now(timezone.utc).isoformat(), "run_id": self.run_id, **record}
        with open(self.path, "a") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def append_response(self, iteration: int, response: dict, usage: Any) -> None:
        """Audit line for the model turn (redacted); not a resume checkpoint."""
        self._write(
            {
                "phase": "response",
                "iteration": iteration,
                "response": redact_secrets(response),
                "usage": {
                    "input_tokens": getattr(usage, "input_tokens", 0),
                    "output_tokens": getattr(usage, "output_tokens", 0),
                },
            }
        )

    def append_in_flight(self, iteration: int, tool_use: dict) -> int:
        """Write the ``in_flight`` line, flush, and return the ``seq`` the
        matching close will reuse. Called BEFORE dispatch."""
        self._seq += 1
        seq = self._seq
        tool = tool_use.get("name", "")
        params = tool_use.get("input", {}) or {}
        self._write(
            {
                "seq": seq,
                "phase": "in_flight",
                "iteration": iteration,
                "step": tool_use.get("step"),
                "tool": tool,
                "params": redact_secrets(params),
                "idem": _idem(tool, params),
            }
        )
        return seq

    def append_done(self, seq: int, result: dict) -> None:
        """Write the ``done`` close (redacted), flush. Called AFTER dispatch."""
        self._write(
            {"seq": seq, "phase": "done", "status": "ok", "result": redact_secrets(result)}
        )

    def append_error(self, seq: int, err: Exception) -> None:
        """Write the ``error`` close, flush. Called AFTER dispatch."""
        self._write({"seq": seq, "phase": "error", "status": "error", "error": str(err)})

    def append_await_user(self, request: dict) -> None:
        """Write an ``await_user`` line on the *current* (still-open) ``seq``,
        flush. A HITL tool pauses inside its dispatch -- the loop wrote the
        ``in_flight`` line just before -- so this line shares that action's
        ``seq``, and a crash while waiting resumes into the same pending
        request. Redacted on write like every other line."""
        self._write(
            {
                "seq": self._seq,
                "phase": "await_user",
                "request": redact_secrets(request),
            }
        )


@dataclass
class ResumeState:
    """The purified view a resume continues from -- goal-relevant records, not
    the whole transcript. ``next_seq`` is the first uncompleted step."""

    run_id: str
    last_seq: int
    next_seq: int
    dangling: dict | None
    completed_seqs: list[int] = field(default_factory=list)
    recent_results: list[dict] = field(default_factory=list)


def _read_records(path: str) -> list[dict]:
    records: list[dict] = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _dangling_in_flight(records: list[dict]) -> dict | None:
    """The unclosed ``in_flight`` record (a crash mid-action), or ``None``.
    A ``seq`` is closed once a ``done``/``error`` line reuses it."""
    in_flight: dict[int, dict] = {}
    for rec in records:
        if "seq" not in rec:
            continue
        phase = rec.get("phase")
        if phase == "in_flight":
            in_flight[rec["seq"]] = rec
        elif phase in ("done", "error"):
            in_flight.pop(rec["seq"], None)
    if not in_flight:
        return None
    # The latest still-open action.
    return in_flight[max(in_flight)]


def find_latest(runs_dir: str | None = None) -> str | None:
    """Newest run dir whose journal is unfinished (has a dangling
    ``in_flight``), or ``None``."""
    base = Path(runs_dir) if runs_dir else _default_runs_dir()
    if not base.is_dir():
        return None
    candidates: list[tuple[float, str]] = []
    for run_dir in base.iterdir():
        journal = run_dir / "trajectory.jsonl"
        if not journal.is_file():
            continue
        if _dangling_in_flight(_read_records(str(journal))) is not None:
            candidates.append((journal.stat().st_mtime, run_dir.name))
    if not candidates:
        return None
    return max(candidates)[1]


async def resume(
    run_id: str, runs_dir: str | None = None, path: str | None = None
) -> ResumeState:
    """Read the journal TAIL, classify the last ``seq`` (closed or dangling
    ``in_flight``), reconstruct a purified context, and return a ``ResumeState``
    positioned at the first uncompleted step. The giant transcript is never
    read; completed steps are never re-run. A dangling action is re-validated
    live via its ``idem`` before any re-do -- never blindly replayed."""
    if path is None:
        base = Path(runs_dir) if runs_dir else _default_runs_dir()
        path = str(base / run_id / "trajectory.jsonl")

    records = _read_records(path)
    seqs = [r["seq"] for r in records if "seq" in r]
    last_seq = max(seqs) if seqs else -1

    dangling = _dangling_in_flight(records)
    closed = {
        r["seq"]
        for r in records
        if r.get("phase") in ("done", "error") and "seq" in r
    }
    completed_seqs = sorted(closed)
    recent_results = [
        r.get("result", {})
        for r in records
        if r.get("phase") == "done"
    ][-3:]

    if dangling is not None:
        next_seq = dangling["seq"]
    else:
        next_seq = last_seq + 1

    return ResumeState(
        run_id=run_id,
        last_seq=last_seq,
        next_seq=next_seq,
        dangling=dangling,
        completed_seqs=completed_seqs,
        recent_results=recent_results,
    )

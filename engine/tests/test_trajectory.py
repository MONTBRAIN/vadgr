"""The append-only JSONL resume journal.

One monotonic ``seq``, code-enforced by the loop: every tool call writes
``in_flight`` before dispatch and ``done``/``error`` after, so a mid-action
crash always leaves a dangling record -- the signal resume keys on. Secrets are
redacted on write, so the one file is both audit trail and resume source.
"""

import json

import pytest

from engine.loop import Usage
from engine.trajectory import (
    Trajectory,
    find_latest,
    is_secret_key,
    resume,
)


def _read_lines(path) -> list[dict]:
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _tool_use(name="browser__click", params=None, tid="t1", step="book-flight"):
    return {"id": tid, "name": name, "input": params or {"x": 1}, "step": step}


def test_in_flight_then_done_share_one_seq_in_order(tmp_path):
    journal = tmp_path / "trajectory.jsonl"
    traj = Trajectory("run-1", path=str(journal))

    seq = traj.append_in_flight(0, _tool_use())
    traj.append_done(seq, {"ok": True})

    lines = _read_lines(journal)
    assert len(lines) == 2
    assert lines[0]["phase"] == "in_flight"
    assert lines[1]["phase"] == "done"
    assert lines[0]["seq"] == lines[1]["seq"] == seq
    assert lines[1]["status"] == "ok"
    # The in_flight line carries the durable-action metadata.
    assert lines[0]["tool"] == "browser__click"
    assert lines[0]["step"] == "book-flight"
    assert lines[0]["idem"].startswith("sha256:")


def test_seq_is_monotonic_across_tool_calls(tmp_path):
    traj = Trajectory("run-1", path=str(tmp_path / "t.jsonl"))
    s0 = traj.append_in_flight(0, _tool_use(tid="a"))
    traj.append_done(s0, {"ok": True})
    s1 = traj.append_in_flight(1, _tool_use(tid="b"))
    traj.append_done(s1, {"ok": True})
    assert s1 == s0 + 1


def test_append_error_writes_error_close(tmp_path):
    journal = tmp_path / "t.jsonl"
    traj = Trajectory("run-1", path=str(journal))
    seq = traj.append_in_flight(0, _tool_use())
    traj.append_error(seq, RuntimeError("boom"))

    close = _read_lines(journal)[1]
    assert close["seq"] == seq
    assert close["phase"] == "error"
    assert close["status"] == "error"
    assert "boom" in close["error"]


def test_secrets_are_redacted_on_write(tmp_path):
    journal = tmp_path / "t.jsonl"
    traj = Trajectory("run-1", path=str(journal))

    secret = "sk-ant-oat01-VERYSECRETTOKEN"  # secret-scan: allow-test-fixture
    seq = traj.append_in_flight(
        0, _tool_use(params={"api_key": secret, "note": "hello"})
    )
    traj.append_done(seq, {"access_token": secret, "value": "kept"})

    raw = journal.read_text()
    assert secret not in raw
    # Non-secret fields survive.
    assert "hello" in raw
    assert "kept" in raw


def test_append_response_is_an_audit_line_not_a_checkpoint(tmp_path):
    journal = tmp_path / "t.jsonl"
    traj = Trajectory("run-1", path=str(journal))

    class _Usage:
        input_tokens = 10
        output_tokens = 4

    traj.append_response(0, {"content": [{"type": "text", "text": "hi"}]}, _Usage())
    line = _read_lines(journal)[0]
    assert line["phase"] == "response"
    assert line["iteration"] == 0


@pytest.mark.asyncio
async def test_resume_detects_dangling_in_flight_and_positions_at_it(tmp_path):
    journal = tmp_path / "t.jsonl"
    traj = Trajectory("run-danger", path=str(journal))
    # Two completed steps...
    s0 = traj.append_in_flight(0, _tool_use(tid="a"))
    traj.append_done(s0, {"ok": 1})
    s1 = traj.append_in_flight(1, _tool_use(tid="b"))
    traj.append_done(s1, {"ok": 2})
    # ...then a crash mid-action: an unclosed in_flight is the last line.
    s2 = traj.append_in_flight(2, _tool_use(tid="c", step="charge-card"))

    state = await resume("run-danger", runs_dir=str(tmp_path.parent), path=str(journal))

    assert state.last_seq == s2
    assert state.dangling is not None
    assert state.dangling["seq"] == s2
    assert state.dangling["step"] == "charge-card"
    # Positioned AT the dangling step -- completed steps are not re-run.
    assert state.next_seq == s2
    assert state.completed_seqs == [s0, s1]


@pytest.mark.asyncio
async def test_resume_after_clean_close_positions_after_last(tmp_path):
    journal = tmp_path / "t.jsonl"
    traj = Trajectory("run-clean", path=str(journal))
    s0 = traj.append_in_flight(0, _tool_use())
    traj.append_done(s0, {"ok": True})

    state = await resume("run-clean", path=str(journal))
    assert state.dangling is None
    assert state.next_seq == s0 + 1
    assert state.completed_seqs == [s0]


def test_find_latest_picks_newest_unfinished_run(tmp_path):
    runs = tmp_path / "runs"
    # A finished run (all closed).
    done_dir = runs / "run-done"
    done_dir.mkdir(parents=True)
    dt = Trajectory("run-done", path=str(done_dir / "trajectory.jsonl"))
    s = dt.append_in_flight(0, _tool_use())
    dt.append_done(s, {"ok": True})

    # An unfinished run (dangling in_flight).
    open_dir = runs / "run-open"
    open_dir.mkdir(parents=True)
    ot = Trajectory("run-open", path=str(open_dir / "trajectory.jsonl"))
    ot.append_in_flight(0, _tool_use())

    assert find_latest(runs_dir=str(runs)) == "run-open"


def test_find_latest_returns_none_when_all_finished(tmp_path):
    runs = tmp_path / "runs"
    d = runs / "run-done"
    d.mkdir(parents=True)
    t = Trajectory("run-done", path=str(d / "trajectory.jsonl"))
    s = t.append_in_flight(0, _tool_use())
    t.append_done(s, {"ok": True})
    assert find_latest(runs_dir=str(runs)) is None


def test_usage_counts_survive_redaction(tmp_path):
    """Regression (E2E/0.4.0 F6): the key pattern matched the substring
    ``token``, so ``input_tokens`` / ``output_tokens`` were redacted and usage
    could not be reconstructed from the journal -- the durable record."""
    journal = tmp_path / "t.jsonl"
    traj = Trajectory("run-1", path=str(journal))

    traj.append_response(
        0,
        {
            "content": [{"type": "text", "text": "hi"}],
            "usage": {"input_tokens": 2759, "output_tokens": 128},
        },
        Usage(input_tokens=2759, output_tokens=128),
    )

    record = json.loads(journal.read_text().strip())
    # The loop's own accounting line was never routed through redaction...
    assert record["usage"] == {"input_tokens": 2759, "output_tokens": 128}
    # ...but the provider's response, which IS redacted, carries the same counts
    # and used to arrive as "[REDACTED]".
    assert record["response"]["usage"] == {
        "input_tokens": 2759,
        "output_tokens": 128,
    }


def test_secret_keys_are_matched_as_whole_words():
    """Credentials are redacted whichever way the key is spelled; counts and
    limits that merely contain the word are not."""
    for key in (
        "token",
        "access_token",
        "accessToken",
        "refresh-token",
        "api_key",
        "apiKey",
        "client_secret",
        "Authorization",
        "password",
        "session_key",
    ):
        assert is_secret_key(key), key

    for key in (
        "input_tokens",
        "output_tokens",
        "total_input_tokens",
        "max_tokens",
        "tokens_used",
        "stop_reason",
        "message",
        "auth_mode",
    ):
        assert not is_secret_key(key), key

"""Resume as a thing the loop can actually be started from.

`0.4.0` shipped `find_latest()` and `resume()` and nothing called them, because
`run_loop` took a task and started at zero: a `ResumeState` had nowhere to go.
Gate clause 2 is a mid-run kill resuming from the journal, so that gap is what
made the clause undemonstrable on the product however correct the library was.
"""

import json

from engine.loop import _opening_messages
from engine.trajectory import ResumeState, Trajectory


def _state(**kw):
    base = dict(run_id="r", last_seq=3, next_seq=3, dangling=None,
                completed_seqs=[0, 1, 2], recent_results=[])
    base.update(kw)
    return ResumeState(**base)


def test_a_fresh_run_is_unchanged():
    """No resume state means byte-identical behaviour to 0.4.0."""
    assert _opening_messages("do the thing", None) == [
        {"role": "user", "content": "do the thing"}
    ]


def test_a_resumed_run_keeps_the_goal_and_is_told_what_is_done():
    messages = _opening_messages("do the thing", _state())
    assert messages[0] == {"role": "user", "content": "do the thing"}
    note = messages[1]["content"]
    assert "3 steps already completed" in note
    assert "do not repeat them" in note


def test_the_note_is_a_user_turn_not_a_fabricated_assistant_turn():
    """Claiming the model said something it did not say invites it to
    elaborate on work it has no memory of doing."""
    assert all(m["role"] == "user" for m in _opening_messages("t", _state()))


def test_the_transcript_is_not_replayed_into_the_context():
    """The point of resume is not paying twice for what already ran.

    Feeding the journal back would re-send every screenshot and tool result the
    crashed process already spent tokens on.
    """
    huge = [{"screenshot": "A" * 50_000}]
    messages = _opening_messages("t", _state(recent_results=huge))
    assert len(json.dumps(messages)) < 5_000


def test_one_completed_step_reads_as_singular():
    note = _opening_messages("t", _state(completed_seqs=[0]))[1]["content"]
    assert "1 step already completed" in note


def test_a_resumed_journal_continues_its_seq_instead_of_colliding(tmp_path):
    """The seq pairs an in_flight with its done.

    A resumed run that restarted at 0 would write a second record numbered 0,
    leaving the record it is resuming from unmatched forever - the journal would
    permanently look mid-crash.
    """
    path = tmp_path / "t.jsonl"
    first = Trajectory("r", path=str(path))
    seq_a = first.append_in_flight(0, {"name": "a", "input": {}})
    first.append_done(seq_a, {"ok": True})
    seq_b = first.append_in_flight(1, {"name": "b", "input": {}})   # the crash

    resumed = Trajectory("r", path=str(path), start_seq=seq_b)
    seq_c = resumed.append_in_flight(2, {"name": "c", "input": {}})

    assert (seq_a, seq_b, seq_c) == (0, 1, 2)
    seqs = [json.loads(l)["seq"] for l in path.read_text().splitlines()
            if "seq" in json.loads(l)]
    assert seqs == sorted(seqs), "seq must stay monotonic across a resume"

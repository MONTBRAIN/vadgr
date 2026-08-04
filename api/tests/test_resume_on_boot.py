"""Resume, from the daemon's side.

`E2E/0.4.0/e2e.md` Part R proved the *library* resumes and said in as many words
that it did not prove the daemon does, because nothing called it. Gate clause 2
is a mid-run kill resuming from the journal, so this is the test that makes the
clause about the product rather than about a function.
"""

import json

import pytest

from api.services.execution_service import find_resumable_runs, resume_interrupted_runs


def _journal(tmp_path, run_id, *, records):
    d = tmp_path / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "trajectory.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n"
    )
    return str(tmp_path)


DONE_PAIR = [
    {"run_id": "r", "seq": 0, "phase": "in_flight", "tool": "a", "params": {}},
    {"run_id": "r", "seq": 0, "phase": "done", "status": "ok", "result": {"ok": True}},
]


@pytest.mark.asyncio
async def test_a_clean_journal_is_not_resumed(tmp_path):
    """A run that finished is finished. Resuming it would re-run work whose
    side effects already happened."""
    runs = _journal(tmp_path, "r", records=DONE_PAIR)
    assert await find_resumable_runs(runs) == []
    assert await resume_interrupted_runs(runs_dir=runs) == []


@pytest.mark.asyncio
async def test_no_journals_at_all_is_a_no_op(tmp_path):
    """First boot on a fresh machine must not be a special case."""
    assert await resume_interrupted_runs(runs_dir=str(tmp_path)) == []


@pytest.mark.asyncio
async def test_a_dangling_in_flight_is_resumed(tmp_path):
    runs = _journal(tmp_path, "r", records=DONE_PAIR + [
        {"run_id": "r", "seq": 1, "phase": "in_flight", "tool": "b", "params": {}},
    ])
    assert await find_resumable_runs(runs) == ["r"]
    assert await resume_interrupted_runs(runs_dir=runs) == ["r"]


@pytest.mark.asyncio
async def test_it_continues_from_the_dangling_step_and_does_not_redo_the_done_one(
    tmp_path,
):
    """The distinction that matters, and the one an outcome cannot show.

    A replayed run also ends `completed`, so "it finished after a restart"
    proves nothing. What proves it is the position: the state handed to the
    daemon starts at the UNcompleted step, so the completed one is not a step
    the loop will run again.
    """
    from engine.trajectory import resume

    runs = _journal(tmp_path, "r", records=DONE_PAIR + [
        {"run_id": "r", "seq": 1, "phase": "in_flight", "tool": "b", "params": {}},
    ])
    resumed = await resume_interrupted_runs(runs_dir=runs)
    assert resumed == ["r"]

    state = await resume("r", runs_dir=runs)
    assert state.completed_seqs == [0]      # the finished step
    assert state.next_seq == 1              # continue AT the dangling one
    assert state.dangling["tool"] == "b"
    assert 0 not in range(state.next_seq, state.next_seq + 1), "seq 0 must not re-run"


@pytest.mark.asyncio
async def test_the_service_is_told_to_continue_each_resumable_run(tmp_path):
    """Startup does not just report; it hands the run back to the service."""
    runs = _journal(tmp_path, "r", records=DONE_PAIR + [
        {"run_id": "r", "seq": 1, "phase": "in_flight", "tool": "b", "params": {}},
    ])

    continued = []

    class FakeService:
        async def continue_run(self, run_id, state):
            continued.append((run_id, state.next_seq))

    await resume_interrupted_runs(FakeService(), runs_dir=runs)
    assert continued == [("r", 1)]

"""The shared tool-use loop, wired against fakes.

A scripted ``llm_call`` + a fake ``MCPHost`` + a spy ``Trajectory`` prove the
loop dispatches tools, journals ``in_flight`` before dispatch and ``done``/
``error`` after, prunes images each iteration, captures a tool error as an
``is_error`` result, and returns a ``RunResult``.
"""

import copy

import pytest

from engine.loop import MaxIterationsExceeded, run_loop


def _tool_use_response(tid="t1", name="cua__click", inp=None, in_tok=10, out_tok=5):
    return {
        "content": [
            {"type": "text", "text": "working"},
            {"type": "tool_use", "id": tid, "name": name, "input": inp or {"x": 1}},
        ],
        "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
    }


def _final_response(text="all done", in_tok=3, out_tok=2):
    return {
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
    }


class ScriptedLLM:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def __call__(self, messages, tools, max_tokens):
        self.calls.append({"messages": copy.deepcopy(messages), "tools": tools})
        if len(self._responses) == 1:
            return self._responses[0]
        return self._responses.pop(0)


class FakeMCP:
    def __init__(self, log, handler=None):
        self.log = log
        self._handler = handler or (lambda tu: {"content": "ok"})
        self.dispatched = []

    def tools(self):
        return [{"name": "cua__click"}]

    async def dispatch(self, tool_use):
        self.log.append(("dispatch", tool_use["id"]))
        self.dispatched.append(tool_use)
        return self._handler(tool_use)


class SpyTrajectory:
    def __init__(self, log):
        self.log = log
        self._seq = -1

    def append_response(self, iteration, response, usage):
        self.log.append(("response", iteration))

    def append_in_flight(self, iteration, tool_use):
        self._seq += 1
        self.log.append(("in_flight", self._seq))
        return self._seq

    def append_done(self, seq, result):
        self.log.append(("done", seq))

    def append_error(self, seq, err):
        self.log.append(("error", seq))


class EventSink:
    def __init__(self):
        self.events = []

    async def __call__(self, event):
        self.events.append(event)


@pytest.mark.asyncio
async def test_dispatches_tool_and_returns_run_result():
    log = []
    llm = ScriptedLLM([_tool_use_response(), _final_response()])
    mcp = FakeMCP(log)
    traj = SpyTrajectory(log)

    result = await run_loop(llm, "do it", mcp, traj, EventSink())

    assert len(mcp.dispatched) == 1
    assert mcp.dispatched[0]["name"] == "cua__click"
    assert result.final_text == "all done"
    assert result.total_iterations == 2
    assert result.total_input_tokens == 13   # 10 + 3
    assert result.total_output_tokens == 7   # 5 + 2
    assert result.trajectory is traj


@pytest.mark.asyncio
async def test_journals_in_flight_before_dispatch_and_done_after():
    log = []
    llm = ScriptedLLM([_tool_use_response(), _final_response()])
    mcp = FakeMCP(log)

    await run_loop(llm, "do it", mcp, SpyTrajectory(log), EventSink())

    phases = [entry[0] for entry in log]
    i_in_flight = phases.index("in_flight")
    i_dispatch = phases.index("dispatch")
    i_done = phases.index("done")
    assert i_in_flight < i_dispatch < i_done


@pytest.mark.asyncio
async def test_prunes_images_every_iteration(monkeypatch):
    calls = {"n": 0}
    import engine.loop as loop_mod

    real = loop_mod.prune_old_images

    def counting_prune(messages, keep_last=3):
        calls["n"] += 1
        return real(messages, keep_last=keep_last)

    monkeypatch.setattr(loop_mod, "prune_old_images", counting_prune)

    llm = ScriptedLLM([_tool_use_response(), _final_response()])
    result = await run_loop(llm, "do it", FakeMCP([]), SpyTrajectory([]), EventSink())

    assert calls["n"] == result.total_iterations == 2


@pytest.mark.asyncio
async def test_tool_error_captured_as_is_error_not_a_crash():
    log = []

    def boom(tool_use):
        raise RuntimeError("nope")

    llm = ScriptedLLM([_tool_use_response(), _final_response()])
    mcp = FakeMCP(log, handler=boom)

    result = await run_loop(llm, "do it", mcp, SpyTrajectory(log), EventSink())

    # The error was journaled as an error close, not swallowed.
    assert any(entry[0] == "error" for entry in log)
    # The failed tool came back to the model as an is_error tool_result.
    fed_back = llm.calls[1]["messages"][-1]["content"][0]
    assert fed_back["type"] == "tool_result"
    assert fed_back["is_error"] is True
    assert "nope" in fed_back["content"]
    # The run still completed normally.
    assert result.final_text == "all done"


@pytest.mark.asyncio
async def test_emits_llm_response_and_tool_call_complete_events():
    sink = EventSink()
    llm = ScriptedLLM([_tool_use_response(), _final_response()])

    await run_loop(llm, "do it", FakeMCP([]), SpyTrajectory([]), sink)

    types = [e["type"] for e in sink.events]
    assert types.count("llm_response") == 2
    assert types.count("tool_call_complete") == 1


@pytest.mark.asyncio
async def test_raises_max_iterations_exceeded_when_agent_never_finishes():
    llm = ScriptedLLM([_tool_use_response()])  # single element -> always tool_use

    with pytest.raises(MaxIterationsExceeded):
        await run_loop(
            llm, "loop forever", FakeMCP([]), SpyTrajectory([]), EventSink(),
            max_iterations=3,
        )

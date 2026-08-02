"""The seam between the loop and the executor.

The loop pushes, the executor pulls, and this bridge is the join. What these
tests guard is not that events arrive but that the RIGHT ones do: an adapter
that forwards everything is how a base64 screenshot ends up going through a
phone's socket.
"""

import asyncio

import pytest

from api.engine.native_bridge import NativeLoopProvider, map_event


class FakeResult:
    def __init__(self, text="done"):
        self.final_text = text


class FakeProvider:
    """An engine provider that emits a scripted event list, then finishes."""

    def __init__(self, events=(), raise_at_end=None, delay=0.0):
        self.events = list(events)
        self.raise_at_end = raise_at_end
        self.delay = delay
        self.torn_down = False
        self.kwargs = None

    async def setup(self):
        return None

    async def teardown(self):
        self.torn_down = True

    async def run_agent(self, task, mcp_servers, on_event, **kwargs):
        self.kwargs = kwargs
        for e in self.events:
            await on_event(e)
            if self.delay:
                await asyncio.sleep(self.delay)
        if self.raise_at_end:
            raise self.raise_at_end
        return FakeResult()


async def _drain(provider, **kw):
    return [e async for e in provider.execute_streaming("do the thing", **kw)]


# -- the mapping table, row by row -------------------------------------------

def test_text_becomes_output():
    e = map_event({"type": "text", "text": "hello"})
    assert (e.type, e.data) == ("output", "hello")


def test_tool_call_becomes_one_line_naming_the_tool():
    e = map_event(
        {"type": "tool_call_complete", "tool_use": {"name": "control__todo_write"},
         "result": {"ok": True}}
    )
    assert e.type == "output"
    assert "control__todo_write" in e.data and "ok" in e.data


def test_a_failed_tool_says_so():
    e = map_event(
        {"type": "tool_call_complete", "tool_use": {"name": "control__ask_user"},
         "result": {"is_error": True}}
    )
    assert "error" in e.data


def test_progress_and_todos_and_gates_use_the_contract_frame_names():
    """The names are CONTRACT.md's, not ones invented here.

    The phone codegens against the contract, so a frame named `awaiting_approval`
    when the contract says `awaiting` is a rename someone pays for twice - once
    here and once in the client.
    """
    assert map_event({"type": "progress", "message": "reading"}).type == "output"
    assert map_event({"type": "todos", "todos": [{"id": "1"}]}).type == "todos"
    assert map_event({"type": "await_user", "prompt": "ok?"}).type == "awaiting"


def test_the_frames_the_bridge_emits_are_all_in_the_contract():
    """Guards the seam in the direction that actually drifts.

    A frame this bridge invents reaches the socket and the phone has no case for
    it; the phone silently ignores it and the feature looks broken with nothing
    failing. CONTRACT.md section 2.5 is the list.
    """
    contract_frames = {"output", "todos", "awaiting", "done", "error"}
    emitted = set()
    for e in [
        {"type": "text", "text": "x"},
        {"type": "tool_call_complete", "tool_use": {"name": "t"}, "result": {}},
        {"type": "progress", "message": "m"},
        {"type": "todos", "todos": []},
        {"type": "await_user", "prompt": "p"},
    ]:
        mapped = map_event(e)
        if mapped is not None:
            emitted.add(mapped.type)
    assert emitted <= contract_frames, f"not in the contract: {emitted - contract_frames}"


@pytest.mark.parametrize("kind", ["llm_response", "tool_result"])
def test_the_two_unbounded_events_are_dropped(kind):
    """Asserted directly, not inferred from a count.

    `llm_response` is the whole model response and `tool_result` can be a
    screenshot. The journal keeps both; the socket must not carry them.
    """
    assert map_event({"type": kind, "response": {"x": "y" * 10_000}}) is None


def test_an_unknown_event_is_dropped_rather_than_forwarded_blind():
    # A future loop event this bridge has not been taught is exactly the one
    # whose payload nobody has bounded.
    assert map_event({"type": "something_new_in_0_6_0", "blob": "..."}) is None


# -- push becomes pull --------------------------------------------------------

@pytest.mark.asyncio
async def test_every_pushed_event_is_yielded_in_order():
    events = [{"type": "text", "text": str(i)} for i in range(50)]
    out = await _drain(NativeLoopProvider(FakeProvider(events)))
    assert [e.data for e in out[:-1]] == [str(i) for i in range(50)]


@pytest.mark.asyncio
async def test_a_slow_consumer_loses_nothing():
    """The producer must not outrun the consumer.

    The loop emits as fast as the model answers; a phone on a slow link reads
    slower than that. An unbounded queue is the reason nothing is dropped.
    """
    provider = NativeLoopProvider(FakeProvider(
        [{"type": "text", "text": str(i)} for i in range(200)]
    ))
    seen = []
    async for e in provider.execute_streaming("t"):
        seen.append(e)
        await asyncio.sleep(0)  # yield to the producer between every item
    assert len([e for e in seen if e.type == "output"]) == 200


@pytest.mark.asyncio
async def test_the_stream_ends_exactly_once_with_done():
    out = await _drain(NativeLoopProvider(FakeProvider([{"type": "text", "text": "x"}])))
    assert out[-1].type == "done"
    assert [e.type for e in out].count("done") == 1


@pytest.mark.asyncio
async def test_a_loop_that_raises_ends_the_stream_with_error_not_an_exception():
    """A failing run is an outcome the watcher sees, not a crash in the API."""
    out = await _drain(NativeLoopProvider(
        FakeProvider([{"type": "text", "text": "x"}], raise_at_end=RuntimeError("boom"))
    ))
    assert out[-1].type == "error" and "boom" in out[-1].data


@pytest.mark.asyncio
async def test_the_provider_is_torn_down_even_when_the_run_fails():
    fake = FakeProvider([], raise_at_end=RuntimeError("boom"))
    await _drain(NativeLoopProvider(fake))
    assert fake.torn_down


@pytest.mark.asyncio
async def test_resume_state_reaches_the_loop():
    fake = FakeProvider([])
    marker = object()
    await _drain(NativeLoopProvider(fake), run_id="r1", resume_state=marker)
    assert fake.kwargs["resume_state"] is marker
    assert fake.kwargs["run_id"] == "r1"


@pytest.mark.asyncio
async def test_the_timeout_is_accepted_and_ignored():
    """A native run has no wall-clock deadline (PLANS D-55).

    The executor passes a timeout to every provider, so the parameter has to
    exist; honouring it would cap the multi-hour batch the phase gate names.
    """
    out = await _drain(NativeLoopProvider(FakeProvider([{"type": "text", "text": "x"}])),
                       timeout=1)
    assert out[-1].type == "done"


# -- the create path, which unit-testing the bridge never touched -------------

def test_a_native_provider_config_loads_with_a_model_override():
    """Regression, found by E2E/0.4.1 and by nothing else.

    `load_provider_config` appended `--model` to `config["args"]`, and a native
    provider has no argv - it has a module. The KeyError put every agent created
    on the native provider into status `error`, so the wiring shipped in this
    patch was unreachable through the API while every unit test passed.
    """
    from api.engine.providers import load_provider_config

    config = load_provider_config("anthropic_oauth", {"model": "claude-opus-5"})
    assert config is not None

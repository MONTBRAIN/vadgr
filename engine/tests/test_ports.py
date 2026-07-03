"""The core ports are runtime-checkable protocols a concrete can satisfy.

These lock the signatures the rest of vadgr depends on -- the loop and callers
depend on the protocol, never a concrete class.
"""

from engine.auth.base import AuthStrategy
from engine.base import AgentProvider, RunResult
from engine.format.base import MessageFormat
from engine.trajectory import Trajectory


class _Provider:
    name = "fake"
    auth_mode = "none"
    default_model = "m"

    async def setup(self):
        ...

    async def run_agent(self, task, mcp_servers, on_event, **kwargs):
        ...

    async def teardown(self):
        ...


class _Auth:
    async def inject_headers(self, request):
        ...

    async def handle_401(self, response):
        return False


class _Format:
    def to_provider_messages(self, messages):
        return messages

    def to_provider_tools(self, tools):
        return tools

    def from_provider_response(self, response):
        return response


def test_provider_protocol_is_satisfiable():
    assert isinstance(_Provider(), AgentProvider)


def test_auth_protocol_is_satisfiable():
    assert isinstance(_Auth(), AuthStrategy)


def test_format_protocol_is_satisfiable():
    assert isinstance(_Format(), MessageFormat)


def test_run_result_carries_the_journal(tmp_path):
    traj = Trajectory("run-x", path=str(tmp_path / "t.jsonl"))
    result = RunResult(
        final_text="done",
        trajectory=traj,
        total_iterations=1,
        total_input_tokens=5,
        total_output_tokens=2,
    )
    assert result.trajectory is traj
    assert result.final_text == "done"

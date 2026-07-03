"""The provider port -- the only provider abstraction the loop depends on.

The loop and the rest of vadgr depend on ``AgentProvider`` (a ``Protocol``),
never on a concrete provider. Selecting/swapping a provider is a config entry,
with no caller change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

from engine.trajectory import Trajectory


@runtime_checkable
class AgentProvider(Protocol):
    """A native agent provider: auth + endpoint + format, behind one contract.

    Concrete providers compose an auth strategy, a message format, and the
    family endpoint; the loop only ever sees this protocol."""

    name: str
    auth_mode: str          # "oauth" | "api_key" | "subprocess" | "none"
    default_model: str

    async def setup(self) -> None:
        """Fail fast -- validate creds / reachability before any run."""
        ...

    async def run_agent(
        self,
        task: Any,
        mcp_servers: list,
        on_event: Callable[[dict], Awaitable[None]],
        **kwargs: Any,
    ) -> "RunResult":
        """Run one agent task to completion, streaming events via ``on_event``."""
        ...

    async def teardown(self) -> None:
        """Release anything ``setup()`` acquired."""
        ...


@dataclass
class RunResult:
    """The outcome of one agent run.

    ``trajectory`` is the append-only journal (path + records) -- the durable
    record a resume reads -- not an in-memory transcript."""

    final_text: str
    trajectory: Trajectory
    total_iterations: int
    total_input_tokens: int
    total_output_tokens: int

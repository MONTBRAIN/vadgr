"""Sequential DAG runner. Orchestrates agent execution for runs."""

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Coroutine, Optional

from api.engine.dag import DAG
from api.engine.executor import AgentExecutor
from api.engine.native_bridge import (
    NativeLoopProvider,
    build_native_provider,
    is_native_provider,
)
from api.engine.providers import CLIAgentProvider
from api.persistence.repositories import AgentRepository, ProjectRepository, RunRepository

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _ensure_run_output_dirs(forge_path: str, run_id: str) -> None:
    """Create output directories for a run before execution starts.

    Creates {forge_path}/output/{run_id}/inputs/,
    {forge_path}/output/{run_id}/agent_outputs/,
    {forge_path}/output/{run_id}/user_outputs/, and
    {forge_path}/output/{run_id}/agent_logs/ so agents and the
    log writer don't need to mkdir them themselves.
    """
    if not forge_path or not run_id:
        return
    base = _PROJECT_ROOT / forge_path / "output" / run_id
    (base / "inputs").mkdir(parents=True, exist_ok=True)
    (base / "agent_outputs").mkdir(parents=True, exist_ok=True)
    (base / "user_outputs").mkdir(parents=True, exist_ok=True)
    (base / "agent_logs").mkdir(parents=True, exist_ok=True)


EmitFn = Callable[[str, str, dict], Coroutine[Any, Any, None]]
ProviderFactory = Callable[..., Awaitable[CLIAgentProvider]]


class ExecutionService:
    """Runs agents sequentially following the DAG topology."""

    def __init__(
        self,
        agent_repo: AgentRepository,
        run_repo: RunRepository,
        project_repo: Optional[ProjectRepository],
        executor: AgentExecutor,
        emit: EmitFn,
        provider_factory: ProviderFactory | None = None,
    ):
        self.agent_repo = agent_repo
        self.run_repo = run_repo
        self.project_repo = project_repo
        self.executor = executor
        self.emit = emit
        self.provider_factory = provider_factory

    async def _get_run_provider(
        self,
        provider_key: str,
        model: str | None,
        timeout: int | None,
        run_id: str | None = None,
        resume_state: object | None = None,
    ):
        """The provider a run executes on.

        This is the whole of `0.4.1`'s wiring: a provider marked ``kind: native``
        in `providers.yaml` is the engine, and it arrives wrapped in
        `NativeLoopProvider` so the executor keeps iterating the interface it
        already iterates. Anything else is a legacy CLI provider and behaves
        exactly as it did, until those are deleted in Beta.
        """
        if is_native_provider(provider_key):
            return NativeLoopProvider(
                build_native_provider(provider_key, model),
                mcp_servers=[],
            )
        if self.provider_factory is None:
            return self.executor.provider
        return await self.provider_factory(
            provider_key=provider_key,
            model=model,
            timeout=timeout,
        )

    async def continue_run(self, run_id: str, resume_state) -> None:
        """Continue a run a previous process died inside.

        The same path as a fresh run, with one difference that is the whole
        point: the resume state goes to the provider, so the loop opens at the
        first UNcompleted step and appends to the journal it crashed inside
        rather than starting a second one.
        """
        run = await self.run_repo.get(run_id)
        agent = await self.agent_repo.get(run["agent_id"])
        provider_key = run.get("provider") or agent.get("provider")
        if not is_native_provider(provider_key):
            # Only the native path has a journal to resume from. A legacy CLI
            # run that died is dead: the subprocess took its state with it.
            logger.info("run %s is not native; not resuming", run_id)
            return
        provider = await self._get_run_provider(
            provider_key,
            run.get("model") or agent.get("model"),
            None,
            run_id=run_id,
            resume_state=resume_state,
        )
        await self.run_repo.update_status(run_id, "running")
        await self.emit(run_id, "run_resumed", {"from_seq": resume_state.next_seq})

        async def callback(event_type, data):
            await self.emit(run_id, event_type, data)

        await self.executor.execute(
            {**agent, "provider": provider_key},
            run["inputs"],
            callback,
            run_id=run_id,
            provider=provider,
        )

    async def run_standalone_agent(self, run_id: str):
        """Execute a standalone agent run (no project/DAG)."""
        run = await self.run_repo.get(run_id)
        agent = await self.agent_repo.get(run["agent_id"])
        provider_key = run.get("provider") or agent.get("provider")
        model = run.get("model") or agent.get("model")
        # No wall-clock deadline on the native path: what bounds an unattended
        # run is the gate layer and max_iterations, not a stopwatch, and the
        # phase-0 gate is one real batch completing over HOURS (PLANS D-55).
        # The legacy CLI path keeps its ceiling until it is deleted in Beta.
        native = is_native_provider(provider_key)
        timeout = None if native else (1800 if agent.get("computer_use") else 900)
        provider = await self._get_run_provider(
            provider_key, model, timeout, run_id=run_id
        )
        execution_agent = {
            **agent,
            "provider": provider_key,
            "model": model,
        }

        _ensure_run_output_dirs(agent.get("forge_path", ""), run_id)
        await self.run_repo.update_status(run_id, "running")
        await self.emit(run_id, "run_started", {"forge_path": agent.get("forge_path", "")})

        try:
            async def callback(event_type, data):
                await self.emit(run_id, event_type, data)

            result = await self.executor.execute(
                execution_agent,
                run["inputs"],
                callback,
                run_id=run_id,
                provider=provider,
            )
            await self.run_repo.update_status(run_id, "completed", outputs=result)
            await self.emit(run_id, "run_completed", {"outputs": result})
        except asyncio.CancelledError:
            await self.run_repo.update_status(run_id, "failed")
            await self.emit(run_id, "run_failed", {"error": "Run was cancelled"})
            raise
        except Exception as e:
            await self.run_repo.update_status(run_id, "failed", outputs={"error": str(e)})
            await self.emit(run_id, "run_failed", {"error": str(e)})

    async def resume_standalone_agent(self, run_id: str):
        """Resume a failed standalone agent run from the last completed step."""
        run = await self.run_repo.get(run_id)
        agent = await self.agent_repo.get(run["agent_id"])
        provider_key = run.get("provider") or agent.get("provider")
        model = run.get("model") or agent.get("model")
        timeout = 1800 if agent.get("computer_use") else 900
        provider = await self._get_run_provider(provider_key, model, timeout)
        execution_agent = {
            **agent,
            "provider": provider_key,
            "model": model,
        }

        # Don't recreate output dirs -- they exist from the original run
        await self.run_repo.update_status(run_id, "running")
        await self.emit(run_id, "run_resumed", {"forge_path": agent.get("forge_path", "")})

        try:
            async def callback(event_type, data):
                await self.emit(run_id, event_type, data)

            result = await self.executor.execute(
                execution_agent,
                run["inputs"],
                callback,
                run_id=run_id,
                provider=provider,
            )
            await self.run_repo.update_status(run_id, "completed", outputs=result)
            await self.emit(run_id, "run_completed", {"outputs": result})
        except asyncio.CancelledError:
            await self.run_repo.update_status(run_id, "failed")
            await self.emit(run_id, "run_failed", {"error": "Run was cancelled"})
            raise
        except Exception as e:
            await self.run_repo.update_status(run_id, "failed", outputs={"error": str(e)})
            await self.emit(run_id, "run_failed", {"error": str(e)})

    async def run_project(self, run_id: str):
        """Execute a project run following DAG topology."""
        run = await self.run_repo.get(run_id)
        nodes = await self.project_repo.get_nodes(run["project_id"])
        edges = await self.project_repo.get_edges(run["project_id"])

        dag = DAG(nodes=nodes, edges=edges)
        errors = dag.validate()
        if errors:
            await self.run_repo.update_status(
                run_id, "failed", outputs={"error": "Invalid DAG", "details": errors}
            )
            await self.emit(run_id, "run_failed", {"error": "Invalid DAG"})
            return

        await self.run_repo.update_status(run_id, "running")
        await self.emit(run_id, "run_started", {})

        sorted_nodes = dag.topological_sort()
        outputs: dict[str, dict] = {}

        try:
            for node in sorted_nodes:
                agent = await self.agent_repo.get(node["agent_id"])

                if agent["type"] == "input":
                    outputs[node["id"]] = run["inputs"]
                    continue

                if agent["type"] == "approval":
                    await self.run_repo.update_status(run_id, "awaiting_approval")
                    await self.emit(run_id, "approval_required", {
                        "node_id": node["id"],
                        "outputs_so_far": outputs,
                    })
                    return  # Execution pauses here; resumed via approve endpoint

                if agent["type"] == "output":
                    resolved = dag.resolve_inputs(node, outputs)
                    outputs[node["id"]] = resolved
                    continue

                resolved = dag.resolve_inputs(node, outputs)
                merged_inputs = {**run["inputs"], **resolved}

                _ensure_run_output_dirs(agent.get("forge_path", ""), run_id)

                async def callback(event_type, data):
                    await self.emit(run_id, event_type, data)

                result = await self.executor.execute(agent, merged_inputs, callback, run_id=run_id)
                outputs[node["id"]] = result

            final_outputs = {}
            for node_outputs in outputs.values():
                if isinstance(node_outputs, dict):
                    final_outputs.update(node_outputs)

            await self.run_repo.update_status(run_id, "completed", outputs=final_outputs)
            await self.emit(run_id, "run_completed", {"outputs": final_outputs})

        except Exception as e:
            await self.run_repo.update_status(run_id, "failed", outputs={"error": str(e)})
            await self.emit(run_id, "run_failed", {"error": str(e)})

    async def resume_after_approval(self, run_id: str):
        """Resume a project run after approval gate. Re-runs from where it stopped."""
        run = await self.run_repo.get(run_id)
        if run["status"] != "running":
            return
        # For MVP, re-running the full project is acceptable.
        # Future: track which node was paused and resume from there.
        await self.run_project(run_id)


async def find_resumable_runs(runs_dir: str | None = None) -> list[str]:
    """Run ids whose journal ends mid-action, newest first.

    A journal that ends clean is finished, not interrupted: `find_latest()`
    keys on a **dangling** `in_flight`, which is the record the loop writes
    BEFORE dispatch and closes after. Its presence is the only durable evidence
    that a process died inside a tool call.
    """
    from engine.trajectory import find_latest

    run_id = find_latest(runs_dir)
    return [run_id] if run_id else []


async def resume_interrupted_runs(
    execution_service: "ExecutionService | None" = None,
    runs_dir: str | None = None,
) -> list[str]:
    """Continue runs the last process died inside. Called once, at startup.

    **Continue, never replay.** `resume()` returns the first UNcompleted step,
    so work that finished before the kill is not redone. That distinction is the
    whole point and it is not visible from the outcome: a replayed run also ends
    `completed`, so "it finished after a restart" proves nothing on its own. The
    proof is a side effect that did not happen twice.

    Returns the ids it resumed, so a caller (and a test) can see what it did
    rather than infer it from logs.
    """
    from engine.trajectory import resume

    resumed: list[str] = []
    for run_id in await find_resumable_runs(runs_dir):
        state = await resume(run_id, runs_dir=runs_dir)
        if state.dangling is None:
            continue  # clean journal: finished, nothing to continue
        logger.info(
            "resuming run %s from seq %s (%s step(s) already done)",
            run_id, state.next_seq, len(state.completed_seqs),
        )
        resumed.append(run_id)
        if execution_service is not None:
            await execution_service.continue_run(run_id, state)
    return resumed

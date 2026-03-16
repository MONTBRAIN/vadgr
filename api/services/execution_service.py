"""Sequential DAG runner. Orchestrates agent execution for runs."""

import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Coroutine, Optional

from api.engine.dag import DAG
from api.engine.executor import AgentExecutor
from api.engine.providers import CLIAgentProvider
from api.persistence.repositories import AgentRepository, ProjectRepository, RunRepository

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _ensure_run_output_dirs(forge_path: str, run_id: str) -> None:
    """Create output directories for a run before execution starts.

    Creates {forge_path}/output/{run_id}/agent_outputs/ and
    {forge_path}/output/{run_id}/user_outputs/ so agents don't need
    to mkdir themselves.
    """
    if not forge_path or not run_id:
        return
    base = _PROJECT_ROOT / forge_path / "output" / run_id
    (base / "agent_outputs").mkdir(parents=True, exist_ok=True)
    (base / "user_outputs").mkdir(parents=True, exist_ok=True)


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
        timeout: int,
    ) -> CLIAgentProvider:
        if self.provider_factory is None:
            return self.executor.provider
        return await self.provider_factory(
            provider_key=provider_key,
            model=model,
            timeout=timeout,
        )

    async def run_standalone_agent(self, run_id: str):
        """Execute a standalone agent run (no project/DAG)."""
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

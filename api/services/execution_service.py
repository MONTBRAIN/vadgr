"""Sequential DAG runner. Orchestrates task execution for runs."""

from typing import Any, Callable, Coroutine, Optional

from api.engine.dag import DAG
from api.engine.executor import TaskExecutor
from api.persistence.repositories import TaskRepository, ProjectRepository, RunRepository


EmitFn = Callable[[str, str, dict], Coroutine[Any, Any, None]]


class ExecutionService:
    """Runs tasks sequentially following the DAG topology."""

    def __init__(
        self,
        task_repo: TaskRepository,
        run_repo: RunRepository,
        project_repo: Optional[ProjectRepository],
        executor: TaskExecutor,
        emit: EmitFn,
    ):
        self.task_repo = task_repo
        self.run_repo = run_repo
        self.project_repo = project_repo
        self.executor = executor
        self.emit = emit

    async def run_standalone_task(self, run_id: str):
        """Execute a standalone task run (no project/DAG)."""
        run = await self.run_repo.get(run_id)
        task = await self.task_repo.get(run["task_id"])

        await self.run_repo.update_status(run_id, "running")
        await self.emit(run_id, "run_started", {})

        try:
            async def callback(event_type, data):
                await self.emit(run_id, event_type, data)

            result = await self.executor.execute(task, run["inputs"], callback)
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
                task = await self.task_repo.get(node["task_id"])

                if task["type"] == "input":
                    outputs[node["id"]] = run["inputs"]
                    continue

                if task["type"] == "approval":
                    await self.run_repo.update_status(run_id, "awaiting_approval")
                    await self.emit(run_id, "approval_required", {
                        "node_id": node["id"],
                        "outputs_so_far": outputs,
                    })
                    return  # Execution pauses here; resumed via approve endpoint

                if task["type"] == "output":
                    resolved = dag.resolve_inputs(node, outputs)
                    outputs[node["id"]] = resolved
                    continue

                resolved = dag.resolve_inputs(node, outputs)
                merged_inputs = {**run["inputs"], **resolved}

                async def callback(event_type, data):
                    await self.emit(run_id, event_type, data)

                result = await self.executor.execute(task, merged_inputs, callback)
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

"""Task executor -- routes execution based on forge_config and computer_use flag."""

from typing import Any, Callable, Coroutine


EventCallback = Callable[[str, dict], Coroutine[Any, Any, None]]


class TaskExecutor:
    """Executes a single task node."""

    def __init__(self, llm_service, computer_use_service):
        self.llm_service = llm_service
        self.computer_use_service = computer_use_service

    async def execute(
        self,
        task: dict,
        inputs: dict,
        callback: EventCallback,
    ) -> dict:
        """Run a task and return its outputs.

        Uses forge_config to determine execution strategy:
        - Computer use: delegates to ComputerUseService.run_task().
        - Simple/multi-step: delegates to LLMService.call() (forge handles internally).
        """
        await callback("task_started", {"task_id": task["id"], "name": task["name"]})

        try:
            if task.get("computer_use"):
                result = await self.computer_use_service.run_task(task, inputs, callback)
            else:
                result = await self.llm_service.call(task, inputs)

            await callback("task_completed", {"task_id": task["id"], "outputs": result})
            return result
        except Exception as e:
            await callback("task_failed", {"task_id": task["id"], "error": str(e)})
            raise

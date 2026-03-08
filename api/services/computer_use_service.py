"""ComputerUseEngine wrapper for desktop automation agents."""

from typing import Any, Callable, Coroutine


EventCallback = Callable[[str, dict], Coroutine[Any, Any, None]]


class ComputerUseService:
    """Wraps the computer_use/ engine for agent execution."""

    def __init__(self):
        self._engine = None
        try:
            from computer_use.core.engine import ComputerUseEngine
            self._engine = ComputerUseEngine()
        except (ImportError, Exception):
            pass

    async def run_agent(
        self, agent: dict, inputs: dict, callback: EventCallback,
    ) -> dict:
        """Run a computer use agent. Returns outputs dict."""
        if self._engine is None:
            return {"success": False, "error": "Computer use engine not available"}

        description = agent.get("description", "")
        if inputs:
            description += "\n\nInputs:\n"
            for k, v in inputs.items():
                description += f"  {k}: {v}\n"

        result = await self._engine.run_task(description)
        return result if isinstance(result, dict) else {"success": True, "result": result}

    @property
    def available(self) -> bool:
        return self._engine is not None

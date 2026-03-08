"""Agent executor -- routes execution to CLI providers or computer use."""

import json
from typing import Any, Callable, Coroutine

from api.engine.providers import CLIAgentProvider, build_agent_prompt


EventCallback = Callable[[str, dict], Coroutine[Any, Any, None]]


class AgentExecutor:
    """Executes a single agent node."""

    def __init__(self, provider: CLIAgentProvider, computer_use_service):
        self.provider = provider
        self.computer_use_service = computer_use_service

    async def execute(
        self,
        agent: dict,
        inputs: dict,
        callback: EventCallback,
    ) -> dict:
        """Run an agent and return its outputs.

        - Computer use agents: delegates to ComputerUseService.
        - All others: builds a prompt and sends to the configured CLI provider.
        """
        await callback("agent_started", {"agent_id": agent["id"], "name": agent["name"]})

        try:
            if agent.get("computer_use"):
                result = await self.computer_use_service.run_agent(agent, inputs, callback)
            else:
                prompt = build_agent_prompt(agent, inputs)
                raw_output = await self.provider.execute(
                    prompt=prompt,
                    workspace=agent.get("forge_path") or None,
                )
                result = self._parse_output(raw_output, agent.get("output_schema", []))

            await callback("agent_completed", {"agent_id": agent["id"], "outputs": result})
            return result
        except Exception as e:
            await callback("agent_failed", {"agent_id": agent["id"], "error": str(e)})
            raise

    def _parse_output(self, raw_response: str, output_schema: list[dict]) -> dict:
        """Parse provider response into output dict."""
        try:
            parsed = json.loads(raw_response)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        if output_schema:
            return {output_schema[0]["name"]: raw_response}
        return {"result": raw_response}

"""Agent executor -- routes execution to CLI providers or computer use."""

import json
from pathlib import Path
from typing import Any, Callable, Coroutine

from api.engine.providers import CLIAgentProvider, build_agent_prompt, build_step_prompt

# Project root -- used as fallback workspace so CLI picks up .mcp.json
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)


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
        run_id: str = "",
    ) -> dict:
        """Run an agent and return its outputs.

        - Computer use agents: delegates to ComputerUseService.
        - All others: builds a prompt and sends to the configured CLI provider.

        When the agent has multiple steps, each step runs as a separate
        subprocess. CLI steps use stream-json (live logs), Desktop steps
        use regular json (avoids base64 screenshot crash). Context flows
        between steps through output files.
        """
        await callback("agent_started", {"agent_id": agent["id"], "name": agent["name"]})

        try:
            # CLI providers (claude_code, codex, etc.) handle computer use via
            # MCP/plugins natively. Only route to computer_use_service for the
            # direct anthropic provider, which needs the separate desktop engine.
            use_cu_service = (
                agent.get("computer_use")
                and agent.get("provider") not in ("claude_code", "codex", "aider", "cline", "gemini")
            )
            if use_cu_service:
                result = await self.computer_use_service.run_agent(agent, inputs, callback)
            else:
                steps = agent.get("steps") or []
                has_steps = len(steps) > 1 and agent.get("forge_path")

                if has_steps:
                    result = await self._execute_per_step(agent, inputs, callback, run_id)
                else:
                    result = await self._execute_single(agent, inputs, callback, run_id)

            await callback("agent_completed", {"agent_id": agent["id"], "outputs": result})
            return result
        except Exception as e:
            await callback("agent_failed", {"agent_id": agent["id"], "error": str(e)})
            raise

    async def _execute_single(
        self,
        agent: dict,
        inputs: dict,
        callback: EventCallback,
        run_id: str = "",
    ) -> dict:
        """Run the entire agent as a single subprocess."""
        prompt = build_agent_prompt(agent, inputs, run_id=run_id)
        workspace = _PROJECT_ROOT
        timeout = 1800 if agent.get("computer_use") else 900
        can_stream = not agent.get("computer_use")

        collected_output = ""
        async for event in self.provider.execute_streaming(
            prompt=prompt,
            workspace=workspace,
            timeout=timeout,
            use_stream_json=can_stream,
        ):
            if event.type == "output":
                if can_stream:
                    await callback("agent_log", {
                        "agent_id": agent["id"],
                        "message": event.data,
                    })
            elif event.type == "done":
                collected_output = event.data
            elif event.type == "error":
                raise RuntimeError(event.data)

        return self._parse_output(collected_output, agent.get("output_schema", []))

    async def _execute_per_step(
        self,
        agent: dict,
        inputs: dict,
        callback: EventCallback,
        run_id: str = "",
    ) -> dict:
        """Run each step as a separate subprocess.

        CLI steps use stream-json for live logs. Desktop steps use regular
        json to avoid the base64 screenshot chunk buffer crash. Context
        flows between steps through output files on disk.
        """
        steps = agent.get("steps", [])
        workspace = _PROJECT_ROOT
        last_output = ""

        for i, step in enumerate(steps, 1):
            step_name = step["name"] if isinstance(step, dict) else step
            uses_cu = step.get("computer_use", False) if isinstance(step, dict) else False
            can_stream = not uses_cu
            timeout = 1800 if uses_cu else 900

            await callback("agent_log", {
                "agent_id": agent["id"],
                "message": f"--- Step {i}: {step_name} {'[Desktop]' if uses_cu else '[CLI]'} ---",
            })

            prompt = build_step_prompt(agent, inputs, step_number=i, step=step, run_id=run_id)

            collected_output = ""
            async for event in self.provider.execute_streaming(
                prompt=prompt,
                workspace=workspace,
                timeout=timeout,
                use_stream_json=can_stream,
            ):
                if event.type == "output":
                    if can_stream:
                        await callback("agent_log", {
                            "agent_id": agent["id"],
                            "message": event.data,
                        })
                elif event.type == "done":
                    collected_output = event.data
                elif event.type == "error":
                    raise RuntimeError(
                        f"Step {i} ({step_name}) failed: {event.data}"
                    )

            last_output = collected_output
            await callback("agent_log", {
                "agent_id": agent["id"],
                "message": f"--- Step {i} complete ---",
            })

        return self._parse_output(last_output, agent.get("output_schema", []))

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

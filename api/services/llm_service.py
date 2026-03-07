"""LLM provider abstraction. Builds prompts from task config and calls the provider."""

import json
from typing import Any


class LLMService:
    """Wraps LLM providers (Anthropic, OpenAI). Builds prompts from task description
    and forge_config, calls the provider, and parses output into the declared schema."""

    async def call(self, task: dict, inputs: dict) -> dict:
        """Execute a task via LLM. Returns a dict matching the task's output_schema."""
        prompt = self._build_prompt(task, inputs)
        provider = task.get("provider", "anthropic")
        model = task.get("model", "claude-sonnet-4-6")

        raw_response = await self._call_provider(provider, model, prompt)
        return self._parse_output(raw_response, task.get("output_schema", []))

    def _build_prompt(self, task: dict, inputs: dict) -> str:
        """Build a prompt from task description, forge_config, and inputs."""
        parts = []
        parts.append(f"Task: {task['name']}")
        if task.get("description"):
            parts.append(f"Goal: {task['description']}")

        forge_config = task.get("forge_config", {})
        if forge_config.get("complexity") == "multi_step":
            parts.append(
                f"This is a multi-step task with {forge_config.get('agents', 1)} agents "
                f"and {forge_config.get('steps', 1)} steps."
            )

        if inputs:
            parts.append("Inputs:")
            for key, value in inputs.items():
                parts.append(f"  {key}: {value}")

        output_schema = task.get("output_schema", [])
        if output_schema:
            field_names = [f["name"] for f in output_schema]
            parts.append(f"Return a JSON object with these fields: {', '.join(field_names)}")

        return "\n".join(parts)

    async def _call_provider(self, provider: str, model: str, prompt: str) -> str:
        """Call the actual LLM provider. Override in tests."""
        # MVP: this will be replaced with real Anthropic/OpenAI calls.
        # For now, raise so tests must mock this method.
        raise NotImplementedError(
            f"LLM provider '{provider}' not yet implemented. "
            "Mock this method in tests or configure a provider."
        )

    def _parse_output(self, raw_response: str, output_schema: list[dict]) -> dict:
        """Parse LLM response into output dict. Tries JSON first, falls back to
        mapping the raw text to the first output field."""
        try:
            parsed = json.loads(raw_response)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        if output_schema:
            return {output_schema[0]["name"]: raw_response}
        return {"result": raw_response}

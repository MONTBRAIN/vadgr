"""Agent service -- wraps repository + forge generation."""

import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from api.engine.providers import CLIAgentProvider, ProviderError
from api.persistence.repositories import AgentRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Resolve project root (Agent-Forge/) relative to this file
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class AgentService:
    """Business logic for agent creation. Calls forge to generate agent folders."""

    def __init__(
        self,
        agent_repo: AgentRepository,
        provider: CLIAgentProvider,
        provider_factory: Callable[..., Awaitable[CLIAgentProvider]] | None = None,
    ):
        self.agent_repo = agent_repo
        self.provider = provider
        self.provider_factory = provider_factory

    async def _get_forge_provider(self, agent: dict, timeout: int) -> CLIAgentProvider:
        provider_key = agent.get("provider")
        model = agent.get("model")
        if not provider_key or self.provider_factory is None:
            return self.provider
        return await self.provider_factory(
            provider_key=provider_key,
            model=model,
            timeout=timeout,
        )

    async def create_agent(
        self,
        name: str,
        description: str,
        steps: list | None = None,
        samples: list | None = None,
        input_schema: list | None = None,
        output_schema: list | None = None,
        computer_use: bool = False,
        provider: str = "claude_code",
        model: str = "claude-sonnet-4-6",
    ) -> dict:
        """Create an agent record with status 'creating' and trigger forge generation."""
        return await self.agent_repo.create(
            name=name,
            description=description,
            status="creating",
            steps=steps,
            samples=samples,
            input_schema=input_schema,
            output_schema=output_schema,
            computer_use=computer_use,
            provider=provider,
            model=model,
        )

    async def run_forge(self, agent_id: str) -> None:
        """Run forge to generate the agent folder. Updates agent status on completion.

        Called as a background task after the HTTP response is sent.
        """
        agent = await self.agent_repo.get(agent_id)
        if not agent:
            logger.error("Agent %s not found for forge generation", agent_id)
            return

        try:
            forge_input = {
                "id": agent_id,
                "name": agent["name"],
                "description": agent["description"],
                "samples": agent.get("samples") or [],
                "computer_use": agent.get("computer_use", False),
            }
            if agent.get("steps"):
                forge_input["steps"] = agent["steps"]

            prompt = (
                f"Read forge/api-generate.md and generate an agent from: "
                f"{json.dumps(forge_input)}"
            )

            logger.info("Running forge for agent %s (%s)", agent_id, agent["name"])
            provider = await self._get_forge_provider(agent, timeout=600)
            raw_output = await provider.execute(
                prompt=prompt,
                workspace=str(PROJECT_ROOT),
                timeout=600,  # forge generation can take a while
                raw_output=True,
            )

            # Parse the JSON output from forge
            logger.info("Forge raw output (last 2000 chars): %s", raw_output[-2000:])
            forge_result = self._parse_forge_output(raw_output)
            logger.info("Forge parsed result keys: %s", list(forge_result.keys()))
            logger.info("Forge input_schema: %s", forge_result.get("input_schema", []))
            logger.info("Forge output_schema: %s", forge_result.get("output_schema", []))

            # Ensure forge_path is set -- fall back to known output pattern
            forge_path = forge_result.get("forge_path", "")
            if not forge_path:
                expected = Path(f"output/{agent_id}")
                if (PROJECT_ROOT / expected).exists():
                    forge_path = str(expected)

            # Update the agent with forge results.
            # Only overwrite schemas if forge actually returned them --
            # preserve user-provided schemas from the create call.
            update_fields = {
                "status": "ready",
                "forge_path": forge_path,
                "forge_config": forge_result.get("forge_config", {}),
            }
            if forge_result.get("input_schema"):
                update_fields["input_schema"] = forge_result["input_schema"]
            if forge_result.get("output_schema"):
                update_fields["output_schema"] = forge_result["output_schema"]
            # Forge returns the steps array extracted from the generated agentic.md
            if forge_result.get("steps"):
                update_fields["steps"] = forge_result["steps"]

            await self.agent_repo.update(agent_id, **update_fields)
            logger.info("Forge completed for agent %s -- status: ready", agent_id)

        except ProviderError as e:
            logger.exception("Forge generation failed for agent %s", agent_id)
            await self.agent_repo.update(
                agent_id,
                status="error",
                forge_config={
                    "error": str(e),
                    "stdout": e.stdout,
                    "stderr": e.stderr,
                    "exit_code": e.exit_code,
                },
            )
        except Exception as e:
            logger.exception("Forge generation failed for agent %s", agent_id)
            await self.agent_repo.update(
                agent_id,
                status="error",
                forge_config={"error": str(e)},
            )

    async def run_update(
        self, agent_id: str, old_agent: dict, new_fields: dict
    ) -> None:
        """Re-run forge to update an existing agent's workflow.

        Called as a background task when substantive fields change.
        Status flow: ready → updating → ready/error.
        """
        agent = await self.agent_repo.get(agent_id)
        if not agent:
            logger.error("Agent %s not found for forge update", agent_id)
            return

        try:
            # Build the update input for forge/api-update.md
            original = {
                "name": old_agent.get("name", ""),
                "description": old_agent.get("description", ""),
                "steps": old_agent.get("steps") or [],
                "samples": old_agent.get("samples") or [],
                "computer_use": old_agent.get("computer_use", False),
            }
            updated = {}
            for key in ("description", "steps", "samples", "computer_use"):
                if key in new_fields:
                    updated[key] = new_fields[key]

            update_input = {
                "forge_path": old_agent.get("forge_path", ""),
                "original": original,
                "updated": updated,
            }

            prompt = (
                f"Read forge/api-update.md and update an existing agent from: "
                f"{json.dumps(update_input)}"
            )

            logger.info("Running forge update for agent %s (%s)", agent_id, agent["name"])
            provider = await self._get_forge_provider(agent, timeout=600)
            raw_output = await provider.execute(
                prompt=prompt,
                workspace=str(PROJECT_ROOT),
                timeout=600,
                raw_output=True,
            )

            forge_result = self._parse_forge_output(raw_output)

            update_fields = dict(
                status="ready",
                forge_path=forge_result.get("forge_path", ""),
                forge_config=forge_result.get("forge_config", {}),
                input_schema=forge_result.get("input_schema", []),
                output_schema=forge_result.get("output_schema", []),
            )
            if forge_result.get("steps"):
                update_fields["steps"] = forge_result["steps"]

            await self.agent_repo.update(agent_id, **update_fields)
            logger.info("Forge update completed for agent %s -- status: ready", agent_id)

        except ProviderError as e:
            logger.exception("Forge update failed for agent %s", agent_id)
            await self.agent_repo.update(
                agent_id,
                status="error",
                forge_config={
                    "error": str(e),
                    "stdout": e.stdout,
                    "stderr": e.stderr,
                    "exit_code": e.exit_code,
                },
            )
        except Exception as e:
            logger.exception("Forge update failed for agent %s", agent_id)
            await self.agent_repo.update(
                agent_id,
                status="error",
                forge_config={"error": str(e)},
            )

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """Strip markdown code fences (```json ... ```) from text."""
        import re
        match = re.search(r"```(?:json)?\s*\n(.*?)\n\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text

    def _extract_json_object(self, text: str) -> dict:
        """Find and parse the first valid JSON object in text."""
        # Try direct parse
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        # Strip code fences and retry
        stripped = self._strip_code_fences(text)
        if stripped != text:
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass

        # Scan for JSON object in text
        lines = text.strip().split("\n")
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            if line.startswith("{"):
                try:
                    candidate = "\n".join(lines[i:]).rstrip("`").strip()
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        continue

        raise ValueError(f"Could not parse JSON from text: {text[:500]}")

    def _parse_forge_output(self, raw_output: str) -> dict:
        """Extract the JSON result from forge output.

        Forge may output the JSON wrapped in Claude's JSON output format,
        or it may be raw JSON. Handle both cases.
        """
        # Try direct JSON parse first
        try:
            parsed = json.loads(raw_output)
            # Claude --output-format json wraps in {"type":"result","result":"..."}
            if isinstance(parsed, dict) and "result" in parsed:
                inner = parsed["result"]
                if isinstance(inner, str):
                    return self._extract_json_object(inner)
                if isinstance(inner, dict):
                    return inner
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        return self._extract_json_object(raw_output)

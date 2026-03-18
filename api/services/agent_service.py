"""Agent service -- wraps repository + forge generation."""

import json
import logging
import shutil
import subprocess
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path

from api.engine.providers import CLIAgentProvider, ProviderError
from api.persistence.repositories import AgentRepository
from forge.scripts.src.scaffold import create_venv, install_dependencies

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Resolve project root (Agent-Forge/) relative to this file
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _steps_from_disk(forge_path: str, project_root: Path) -> list[dict]:
    """Scan agent/steps/ and reconstruct steps array from filenames.

    Parses step_NN_step-name.md → {name: "Step Name", computer_use: False}.
    Returns empty list when the directory doesn't exist or forge_path is empty.
    """
    if not forge_path:
        return []
    steps_dir = project_root / forge_path / "agent" / "steps"
    if not steps_dir.is_dir():
        return []
    step_files = sorted(
        f for f in steps_dir.iterdir()
        if f.is_file() and f.name.startswith("step_") and f.suffix == ".md"
    )
    steps = []
    for f in step_files:
        parts = f.stem.split("_", 2)  # ["step", "NN", "step-name"]
        if len(parts) < 3:
            continue
        name = parts[2].replace("-", " ").title()
        steps.append({"name": name, "computer_use": False})
    return steps


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

    def ensure_agent_runtime_scaffold(self, forge_path: str) -> None:
        agent_root = PROJECT_ROOT / forge_path
        if not agent_root.exists():
            return
        output_dir = agent_root / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / ".gitkeep").write_text("")

    def ensure_agent_script_environment(self, forge_path: str) -> None:
        agent_root = PROJECT_ROOT / forge_path
        scripts_dir = agent_root / "agent" / "scripts"
        requirements_path = scripts_dir / "requirements.txt"
        if not scripts_dir.exists() or not requirements_path.exists():
            return

        venv_dir = scripts_dir / ".venv"
        if venv_dir.exists():
            install_dependencies(str(agent_root))
            return
        create_venv(str(agent_root))

    def ensure_agent_repo_tracking(self, forge_path: str, message: str = "Initial agent scaffold") -> None:
        agent_root = PROJECT_ROOT / forge_path
        if not agent_root.exists():
            return
        self.ensure_agent_runtime_scaffold(forge_path)
        gitignore = agent_root / ".gitignore"
        gitignore.write_text(
            "output/*\n"
            "!output/.gitkeep\n"
            "agent/scripts/.venv/\n"
            "__pycache__/\n"
            ".pytest_cache/\n"
            "*.pyc\n"
        )
        if not (agent_root / ".git").exists():
            subprocess.run(["git", "-C", str(agent_root), "init"], check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", str(agent_root), "config", "user.name", "Agent Forge"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(agent_root), "config", "user.email", "agent-forge@local"],
                check=True,
                capture_output=True,
            )
        self._commit_agent_repo(forge_path, message)

    def _commit_agent_repo(self, forge_path: str, message: str) -> None:
        agent_root = PROJECT_ROOT / forge_path
        if not agent_root.exists() or not (agent_root / ".git").exists():
            return
        subprocess.run(["git", "-C", str(agent_root), "add", "."], check=True, capture_output=True)
        status = subprocess.run(
            ["git", "-C", str(agent_root), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        )
        if not status.stdout.strip():
            return
        subprocess.run(
            ["git", "-C", str(agent_root), "commit", "-m", message],
            check=True,
            capture_output=True,
        )

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
            # Populate steps from disk when forge didn't return them and user
            # declared none — avoids overwriting user steps that have computer_use: True.
            if forge_result.get("steps"):
                update_fields["steps"] = forge_result["steps"]
            elif not agent.get("steps") and forge_path:
                disk_steps = _steps_from_disk(forge_path, PROJECT_ROOT)
                if disk_steps:
                    update_fields["steps"] = disk_steps

            await self.agent_repo.update(agent_id, **update_fields)
            if forge_path:
                self.ensure_agent_script_environment(forge_path)
                self.ensure_agent_repo_tracking(forge_path, "Initial agent scaffold")
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

            updated_forge_path = forge_result.get("forge_path", "") or old_agent.get("forge_path", "")
            update_fields = dict(
                status="ready",
                forge_path=updated_forge_path,
                forge_config=forge_result.get("forge_config", {}),
                input_schema=forge_result.get("input_schema", []),
                output_schema=forge_result.get("output_schema", []),
            )
            if forge_result.get("steps"):
                update_fields["steps"] = forge_result["steps"]
            elif not agent.get("steps") and updated_forge_path:
                disk_steps = _steps_from_disk(updated_forge_path, PROJECT_ROOT)
                if disk_steps:
                    update_fields["steps"] = disk_steps

            await self.agent_repo.update(agent_id, **update_fields)
            forge_path = update_fields.get("forge_path", "") or old_agent.get("forge_path", "")
            if forge_path:
                self.ensure_agent_script_environment(forge_path)
                self.ensure_agent_repo_tracking(forge_path, "Update agent workflow")
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

    async def run_import(self, agent_id: str, bundle_bytes: bytes, forge_path: str) -> None:
        """Restore a git bundle into the output folder and mark the agent ready.

        Called as a background task after the HTTP response is sent.
        """
        target_dir = PROJECT_ROOT / forge_path
        try:
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory() as temp_dir:
                bundle_path = Path(temp_dir) / "agent.bundle"
                bundle_path.write_bytes(bundle_bytes)
                subprocess.run(
                    ["git", "clone", str(bundle_path), str(target_dir)],
                    check=True,
                    capture_output=True,
                )
            subprocess.run(
                ["git", "-C", str(target_dir), "config", "user.name", "Agent Forge"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(target_dir), "config", "user.email", "agent-forge@local"],
                check=True,
                capture_output=True,
            )
            self.ensure_agent_runtime_scaffold(forge_path)
            self.ensure_agent_script_environment(forge_path)
            await self.agent_repo.update(agent_id, status="ready")
        except Exception as e:
            logger.exception("Import failed for agent %s", agent_id)
            if target_dir.exists():
                shutil.rmtree(target_dir)
            await self.agent_repo.update(agent_id, status="error", forge_config={"error": str(e)})

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

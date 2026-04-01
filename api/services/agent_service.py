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
            subprocess.run(["git", "-C", str(agent_root), "init"], check=True, capture_output=True, stdin=subprocess.DEVNULL)
            subprocess.run(
                ["git", "-C", str(agent_root), "config", "user.name", "Agent Forge"],
                check=True,
                capture_output=True,
                stdin=subprocess.DEVNULL,
            )
            subprocess.run(
                ["git", "-C", str(agent_root), "config", "user.email", "agent-forge@local"],
                check=True,
                capture_output=True,
                stdin=subprocess.DEVNULL,
            )
        self._commit_agent_repo(forge_path, message)

    def _write_schema_file(self, forge_path: str, input_schema: list, output_schema: list) -> None:
        """Write schema.json to the agent's forge_path for git tracking."""
        agent_root = PROJECT_ROOT / forge_path
        if not agent_root.exists():
            return
        schema_path = agent_root / "schema.json"
        schema_path.write_text(json.dumps({
            "input_schema": input_schema or [],
            "output_schema": output_schema or [],
        }, indent=2) + "\n")

    @staticmethod
    def _format_commit_message(summary: str, provider: str | None = None, model: str | None = None) -> str:
        """Build a standardized commit message with optional provider metadata."""
        if provider and model:
            return f"{summary}\n\nProvider: {provider} ({model})"
        if provider:
            return f"{summary}\n\nProvider: {provider}"
        return f"{summary}\n\nManual edit"

    def commit_schema_change(
        self, forge_path: str, input_schema: list, output_schema: list,
        provider: str | None = None, model: str | None = None,
    ) -> None:
        """Write schema.json and commit it to the agent's git repo."""
        self._write_schema_file(forge_path, input_schema, output_schema)
        msg = self._format_commit_message("Update input/output schemas", provider, model)
        self._commit_agent_repo(forge_path, msg)

    def _commit_agent_repo(self, forge_path: str, message: str) -> None:
        agent_root = PROJECT_ROOT / forge_path
        if not agent_root.exists() or not (agent_root / ".git").exists():
            return
        subprocess.run(["git", "-C", str(agent_root), "add", "."], check=True, capture_output=True, stdin=subprocess.DEVNULL)
        status = subprocess.run(
            ["git", "-C", str(agent_root), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )
        if not status.stdout.strip():
            return
        subprocess.run(
            ["git", "-C", str(agent_root), "commit", "-m", message],
            check=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
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
                # Write schema.json from the latest DB state before committing
                final_agent = await self.agent_repo.get(agent_id)
                self._write_schema_file(
                    forge_path,
                    final_agent.get("input_schema", []),
                    final_agent.get("output_schema", []),
                )
                self.ensure_agent_script_environment(forge_path)
                commit_msg = self._format_commit_message(
                    "Initial agent scaffold",
                    agent.get("provider"), agent.get("model"),
                )
                self.ensure_agent_repo_tracking(forge_path, commit_msg)
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
        self, agent_id: str, old_agent: dict, new_fields: dict,
        provider_override: str | None = None, model_override: str | None = None,
    ) -> None:
        """Re-run forge to update an existing agent's workflow.

        Called as a background task when substantive fields change.
        provider_override/model_override control which provider runs the update
        without changing the agent's stored provider.
        Status flow: ready → updating → ready/error.
        """
        agent = await self.agent_repo.get(agent_id)
        if not agent:
            logger.error("Agent %s not found for forge update", agent_id)
            return

        # Use override provider/model for this forge call, fall back to agent's stored values
        forge_agent = dict(agent)
        if provider_override:
            forge_agent["provider"] = provider_override
        if model_override:
            forge_agent["model"] = model_override

        try:
            # Build the update input for forge/api-update.md
            original = {
                "name": old_agent.get("name", ""),
                "description": old_agent.get("description", ""),
                "steps": old_agent.get("steps") or [],
                "samples": old_agent.get("samples") or [],
                "computer_use": old_agent.get("computer_use", False),
                "input_schema": old_agent.get("input_schema") or [],
                "output_schema": old_agent.get("output_schema") or [],
            }
            updated = {}
            for key in ("description", "steps", "samples", "computer_use", "input_schema", "output_schema"):
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
            provider = await self._get_forge_provider(forge_agent, timeout=600)
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
            )
            # If user explicitly sent schemas, preserve them over forge's.
            # Otherwise use forge's inferred schemas if non-empty.
            if "input_schema" in new_fields:
                update_fields["input_schema"] = new_fields["input_schema"]
            elif forge_result.get("input_schema"):
                update_fields["input_schema"] = forge_result["input_schema"]
            if "output_schema" in new_fields:
                update_fields["output_schema"] = new_fields["output_schema"]
            elif forge_result.get("output_schema"):
                update_fields["output_schema"] = forge_result["output_schema"]
            if forge_result.get("steps"):
                update_fields["steps"] = forge_result["steps"]
            elif not agent.get("steps") and updated_forge_path:
                disk_steps = _steps_from_disk(updated_forge_path, PROJECT_ROOT)
                if disk_steps:
                    update_fields["steps"] = disk_steps

            await self.agent_repo.update(agent_id, **update_fields)
            forge_path = update_fields.get("forge_path", "") or old_agent.get("forge_path", "")
            if forge_path:
                # Write schema.json from the latest DB state before committing
                final_agent = await self.agent_repo.get(agent_id)
                self._write_schema_file(
                    forge_path,
                    final_agent.get("input_schema", []),
                    final_agent.get("output_schema", []),
                )
                self.ensure_agent_script_environment(forge_path)
                # Build descriptive commit message with provider metadata
                changed_parts = [k for k in ("description", "steps", "samples", "computer_use", "input_schema", "output_schema") if k in new_fields]
                summary = f"Update {', '.join(changed_parts)}" if changed_parts else "Update agent workflow"
                commit_msg = self._format_commit_message(
                    summary,
                    forge_agent.get("provider"), forge_agent.get("model"),
                )
                self.ensure_agent_repo_tracking(forge_path, commit_msg)
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
                    stdin=subprocess.DEVNULL,
                )
            subprocess.run(
                ["git", "-C", str(target_dir), "config", "user.name", "Agent Forge"],
                check=True,
                capture_output=True,
                stdin=subprocess.DEVNULL,
            )
            subprocess.run(
                ["git", "-C", str(target_dir), "config", "user.email", "agent-forge@local"],
                check=True,
                capture_output=True,
                stdin=subprocess.DEVNULL,
            )
            self.ensure_agent_runtime_scaffold(forge_path)
            self.ensure_agent_script_environment(forge_path)
            await self.agent_repo.update(agent_id, status="ready")
            # Write schema.json from DB data so imported agents have it on disk
            agent_data = await self.agent_repo.get(agent_id)
            self._write_schema_file(
                forge_path,
                agent_data.get("input_schema", []),
                agent_data.get("output_schema", []),
            )
            msg = self._format_commit_message(
                "Sync schemas after import",
                agent_data.get("provider"), agent_data.get("model"),
            )
            self._commit_agent_repo(forge_path, msg)
        except Exception as e:
            logger.exception("Import failed for agent %s", agent_id)
            if target_dir.exists():
                from api.utils.platform import force_rmtree
                force_rmtree(target_dir)
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

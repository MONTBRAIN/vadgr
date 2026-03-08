"""Config-driven agent providers. One executor class, multiple backends via config.

Provider definitions live in providers.yaml at the project root -- adding a new provider
means editing that YAML file, zero code changes.
"""

import asyncio
import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator

import yaml


class ProviderError(RuntimeError):
    """Raised when a CLI provider exits with non-zero status.

    Carries stdout, stderr, and exit_code for debugging.
    """

    def __init__(self, provider_name: str, exit_code: int, stdout: str, stderr: str):
        self.provider_name = provider_name
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(
            f"Provider '{provider_name}' failed (exit {exit_code}): {stderr}"
        )


@dataclass
class ExecutionEvent:
    """Event emitted during agent execution."""
    type: str  # "output", "error", "done"
    data: str = ""


@dataclass
class ProviderConfig:
    """Configuration for a CLI-based agent provider."""
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    available_check: list[str] = field(default_factory=list)
    timeout: int = 300


def _load_providers_yaml() -> dict[str, dict]:
    """Load provider configs from providers.yaml at the project root."""
    yaml_path = Path(__file__).resolve().parent.parent.parent / "providers.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(
            f"Provider config not found at {yaml_path}. "
            "Create api/providers.yaml with provider definitions."
        )
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    return data.get("providers", {})


def load_provider_config(provider_key: str, overrides: dict | None = None) -> ProviderConfig:
    """Load a provider config by key, optionally applying overrides."""
    providers = _load_providers_yaml()
    if provider_key not in providers:
        raise ValueError(
            f"Unknown provider '{provider_key}'. "
            f"Available: {', '.join(providers.keys())}"
        )
    config = {**providers[provider_key]}
    if overrides:
        config.update(overrides)
    return ProviderConfig(**config)


class CLIAgentProvider:
    """Executes agents by spawning a CLI agentic tool as a subprocess.

    Config-driven: one class handles all providers. Adding a new tool
    means adding a config dict, not a new class.
    """

    def __init__(self, config: ProviderConfig):
        self.config = config

    async def is_available(self) -> bool:
        """Check if the CLI tool is installed."""
        if not self.config.available_check:
            return shutil.which(self.config.command) is not None
        try:
            proc = await asyncio.create_subprocess_exec(
                *self.config.available_check,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            return proc.returncode == 0
        except FileNotFoundError:
            return False

    @staticmethod
    def _clean_env() -> dict[str, str]:
        """Build a subprocess environment without session-nesting env vars."""
        return {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    def _build_args(self, prompt: str, workspace: str | None = None) -> list[str]:
        """Replace placeholders in the config args."""
        result = []
        for arg in self.config.args:
            arg = arg.replace("{{prompt}}", prompt)
            if workspace:
                arg = arg.replace("{{workspace}}", workspace)
            result.append(arg)
        return result

    async def execute(
        self,
        prompt: str,
        workspace: str | None = None,
        timeout: int | None = None,
    ) -> str:
        """Execute a prompt and return the full output."""
        args = self._build_args(prompt, workspace)
        effective_timeout = timeout or self.config.timeout

        proc = await asyncio.create_subprocess_exec(
            self.config.command,
            *args,
            cwd=workspace,
            env=self._clean_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=effective_timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise TimeoutError(
                f"Provider '{self.config.name}' timed out after {effective_timeout}s"
            )

        if proc.returncode != 0:
            raise ProviderError(
                provider_name=self.config.name,
                exit_code=proc.returncode,
                stdout=stdout.decode().strip() if stdout else "",
                stderr=stderr.decode().strip() if stderr else "Unknown error",
            )

        return stdout.decode().strip()

    async def execute_streaming(
        self,
        prompt: str,
        workspace: str | None = None,
        timeout: int | None = None,
    ) -> AsyncIterator[ExecutionEvent]:
        """Execute a prompt and stream output events line by line."""
        args = self._build_args(prompt, workspace)
        effective_timeout = timeout or self.config.timeout

        proc = await asyncio.create_subprocess_exec(
            self.config.command,
            *args,
            cwd=workspace,
            env=self._clean_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            async def read_stream():
                collected = []
                while True:
                    line = await asyncio.wait_for(
                        proc.stdout.readline(),
                        timeout=effective_timeout,
                    )
                    if not line:
                        break
                    text = line.decode().strip()
                    if text:
                        collected.append(text)
                        yield ExecutionEvent(type="output", data=text)

                await proc.wait()
                if proc.returncode != 0:
                    stderr_data = await proc.stderr.read()
                    error_msg = stderr_data.decode().strip() if stderr_data else "Unknown error"
                    yield ExecutionEvent(type="error", data=error_msg)
                else:
                    yield ExecutionEvent(type="done", data="\n".join(collected))

            async for event in read_stream():
                yield event

        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            yield ExecutionEvent(type="error", data=f"Timed out after {effective_timeout}s")


def build_agent_prompt(agent: dict, inputs: dict) -> str:
    """Build the prompt to send to the CLI provider.

    If the agent has a forge_path, instructs the tool to read and follow
    the agentic.md. Otherwise falls back to description-based prompting.
    """
    parts = []

    forge_path = agent.get("forge_path", "")
    if forge_path:
        parts.append(
            f"Read {forge_path}/agentic.md and execute the workflow defined there."
        )
    else:
        parts.append(f"You are an agent named '{agent['name']}'.")
        if agent.get("description"):
            parts.append(f"Your goal: {agent['description']}")

    if inputs:
        parts.append("\nInputs:")
        for key, value in inputs.items():
            parts.append(f"  {key}: {value}")

    output_schema = agent.get("output_schema", [])
    if output_schema:
        field_names = [f["name"] for f in output_schema]
        parts.append(
            f"\nReturn ONLY a JSON object with these fields: {', '.join(field_names)}"
        )
        parts.append("No explanation, no markdown -- just the JSON.")

    return "\n".join(parts)

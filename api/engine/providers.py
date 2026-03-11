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
    # Filter to only fields ProviderConfig accepts (ignore metadata like models)
    valid_fields = {f.name for f in ProviderConfig.__dataclass_fields__.values()}
    config = {k: v for k, v in config.items() if k in valid_fields}
    return ProviderConfig(**config)


def parse_stream_json_line(line: str) -> tuple[str | None, str | None]:
    """Parse a stream-json line into (human_readable_message, final_result).

    Returns:
        - (message, None) for intermediate events worth showing
        - (None, result_str) for the final result event
        - (None, None) for events to skip
    """
    try:
        data = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        # Non-JSON line: return as-is
        return (line if line.strip() else None, None)

    event_type = data.get("type", "")

    if event_type == "result":
        result = data.get("result", "")
        if isinstance(result, dict):
            return (None, json.dumps(result))
        return (None, str(result))

    if event_type == "assistant":
        message = data.get("message", {})
        content_blocks = message.get("content", [])
        for block in content_blocks:
            block_type = block.get("type", "")
            if block_type == "text":
                text = block.get("text", "").strip()
                if text:
                    return (text[:500], None)
            elif block_type == "tool_use":
                tool_name = block.get("name", "unknown")
                return (f"Using tool: {tool_name}", None)

    return (None, None)


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

    def _build_streaming_args(self, prompt: str, workspace: str | None = None) -> list[str]:
        """Build args for streaming: swap --output-format json to stream-json."""
        args = self._build_args(prompt, workspace)
        # Swap json -> stream-json for Claude Code style providers
        swapped = False
        for i, arg in enumerate(args):
            if arg == "json" and i > 0 and args[i - 1] == "--output-format":
                args[i] = "stream-json"
                swapped = True
                break
        # stream-json with --print (-p) requires --verbose
        if swapped:
            args.append("--verbose")
        return args

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
        use_stream_json: bool = True,
    ) -> AsyncIterator[ExecutionEvent]:
        """Execute a prompt and stream output events line by line.

        For providers with --output-format json (e.g. Claude Code), swaps to
        stream-json so output arrives as NDJSON events during execution.
        Parses stream-json events into human-readable messages.

        Set use_stream_json=False for agents that produce very large tool
        results (e.g. computer use screenshots) which exceed the CLI's
        internal stream-json chunk buffer.
        """
        if use_stream_json:
            args = self._build_streaming_args(prompt, workspace)
        else:
            args = self._build_args(prompt, workspace)
        is_stream_json = any(
            args[i] == "stream-json" and i > 0 and args[i - 1] == "--output-format"
            for i in range(len(args))
        )
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
                final_result = None
                while True:
                    line = await asyncio.wait_for(
                        proc.stdout.readline(),
                        timeout=effective_timeout,
                    )
                    if not line:
                        break
                    text = line.decode().strip()
                    if not text:
                        continue

                    if is_stream_json:
                        msg, result = parse_stream_json_line(text)
                        if result is not None:
                            final_result = result
                        elif msg is not None:
                            collected.append(msg)
                            yield ExecutionEvent(type="output", data=msg)
                    else:
                        collected.append(text)
                        yield ExecutionEvent(type="output", data=text)

                await proc.wait()
                if proc.returncode != 0:
                    stderr_data = await proc.stderr.read()
                    error_msg = stderr_data.decode().strip() if stderr_data else "Unknown error"
                    yield ExecutionEvent(type="error", data=error_msg)
                else:
                    done_data = final_result if final_result is not None else "\n".join(collected)
                    yield ExecutionEvent(type="done", data=done_data)

            async for event in read_stream():
                yield event

        except asyncio.TimeoutError:
            yield ExecutionEvent(type="error", data=f"Timed out after {effective_timeout}s")
        finally:
            # Always ensure the subprocess is killed and reaped, even if the
            # caller stops iterating, an exception is raised, or the run fails.
            if proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                await proc.wait()


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

    # Add per-step workflow instructions
    steps = agent.get("steps", [])
    if steps:
        parts.append("\nWorkflow steps (execute in order):")
        for i, step in enumerate(steps, 1):
            step_name = step["name"] if isinstance(step, dict) else step
            uses_cu = step.get("computer_use", False) if isinstance(step, dict) else False
            mode = "DESKTOP" if uses_cu else "CLI"
            parts.append(f"  {i}. [{mode}] {step_name}")
        if any(
            (s.get("computer_use", False) if isinstance(s, dict) else False)
            for s in steps
        ):
            parts.append(
                "\nSteps marked [DESKTOP] require desktop automation: use the "
                "computer_use MCP tools (screenshot, click, type_text, key_press) "
                "to interact with the screen. Open applications, navigate visually, "
                "and capture information by reading screenshots. Do NOT use "
                "web_fetch or curl for [DESKTOP] steps."
            )

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

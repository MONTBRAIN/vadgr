"""Config-driven agent providers. One executor class, multiple backends via config.

Provider definitions live in providers.yaml at the project root -- adding a new provider
means editing that YAML file, zero code changes.
"""

import asyncio
import json
import os
import re
import shutil
import signal
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator

import yaml

# Project root -- used by build_step_prompt to detect step file architecture
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)


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
class StreamingConfig:
    """Provider-specific streaming configuration."""
    mode: str = "none"
    flag: str = ""
    from_value: str = ""
    to_value: str = ""
    extra_args: list[str] = field(default_factory=list)


@dataclass
class ProviderConfig:
    """Configuration for a CLI-based agent provider."""
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    available_check: list[str] = field(default_factory=list)
    timeout: int = 300
    streaming: StreamingConfig | None = None
    stream_parser: str = "plain_text"


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
    model = None
    if overrides:
        model = overrides.get("model")
        config.update(overrides)
    if model:
        config["args"] = [*config["args"], "--model", model]
    if "streaming" in config and isinstance(config["streaming"], dict):
        config["streaming"] = StreamingConfig(
            mode=config["streaming"].get("mode", "none"),
            flag=config["streaming"].get("flag", ""),
            from_value=config["streaming"].get("from", ""),
            to_value=config["streaming"].get("to", ""),
            extra_args=config["streaming"].get("extra_args", []),
        )
    # Filter to only fields ProviderConfig accepts (ignore metadata like models)
    valid_fields = {f.name for f in ProviderConfig.__dataclass_fields__.values()}
    config = {k: v for k, v in config.items() if k in valid_fields}
    return ProviderConfig(**config)


async def create_provider(
    provider_key: str,
    model: str | None = None,
    timeout: int | None = None,
) -> "CLIAgentProvider":
    """Create a provider instance for a specific provider/model selection."""
    overrides = {}
    if model:
        overrides["model"] = model
    if timeout is not None:
        overrides["timeout"] = timeout
    config = load_provider_config(provider_key, overrides or None)
    return CLIAgentProvider(config)


def _parse_claude_stream_json_line(data: dict) -> tuple[str | None, str | None]:
    """Parse Claude stream-json events."""
    event_type = data.get("type", "")

    if event_type == "result":
        result = data.get("result")
        if result is None:
            return (None, None)
        if isinstance(result, dict):
            return (None, json.dumps(result))
        return (None, str(result))

    if event_type != "assistant":
        return (None, None)

    message = data.get("message", {})
    content_blocks = message.get("content", [])
    for block in content_blocks:
        block_type = block.get("type", "")
        if block_type == "text":
            text = block.get("text", "").strip()
            if text:
                return (text[:500], None)
        if block_type == "tool_use":
            tool_name = block.get("name", "unknown")
            return (f"Using tool: {tool_name}", None)

    return (None, None)


def _parse_gemini_stream_json_line(data: dict) -> tuple[str | None, str | None]:
    """Parse Gemini stream-json events."""
    event_type = data.get("type", "")

    if event_type == "message" and data.get("role") == "assistant":
        content = data.get("content", "")
        if isinstance(content, str):
            text = content.strip()
            if text:
                return (text[:500], None)
        return (None, None)

    if event_type == "result":
        result = data.get("result")
        if result is None:
            return (None, None)
        if isinstance(result, dict):
            return (None, json.dumps(result))
        return (None, str(result))

    return (None, None)


def _parse_codex_jsonl_line(data: dict) -> tuple[str | None, str | None]:
    """Parse Codex JSONL events."""
    event_type = data.get("type", "")

    if event_type == "agent_message_delta":
        delta = data.get("delta", "")
        if isinstance(delta, str):
            text = delta.strip()
            if text:
                return (text[:500], None)
        return (None, None)

    item = data.get("item", {})
    item_type = item.get("type", "")

    if event_type == "item.started" and item_type == "command_execution":
        command = item.get("command", "")
        summary = _summarize_command(command)
        if summary:
            return (f"Running command: {summary}", None)
        return ("Running command", None)

    if event_type == "item.completed" and item_type == "reasoning":
        text = _strip_markdown_emphasis(item.get("text", ""))
        if text:
            return (text[:500], None)
        return (None, None)

    if event_type == "item.completed" and item_type == "agent_message":
        text = item.get("text", "")
        if isinstance(text, str):
            cleaned = text.strip()
            if cleaned:
                return (cleaned[:500], None)
        return (None, None)

    if event_type == "item.completed" and item_type == "command_execution":
        return (None, None)

    if event_type in {"response.completed", "result"}:
        result = data.get("result") or data.get("output_text")
        if result is None:
            return (None, None)
        if isinstance(result, dict):
            return (None, json.dumps(result))
        return (None, str(result))

    return (None, None)


def _strip_markdown_emphasis(text: str) -> str:
    """Remove simple markdown emphasis markers from short status text."""
    if not isinstance(text, str):
        return ""
    return re.sub(r"[*_`]+", "", text).strip()


def _summarize_command(command: str) -> str:
    """Extract a short human-readable command summary."""
    if not isinstance(command, str) or not command.strip():
        return ""

    normalized = command.strip()
    for separator in (" && ", "; "):
        if separator in normalized:
            normalized = normalized.split(separator)[-1].strip()
    normalized = normalized.strip("'\"")

    if normalized.startswith("cat <<"):
        return "write file"

    return normalized[:120]


def parse_stream_json_line(
    line: str,
    parser_name: str = "claude_stream_json",
) -> tuple[str | None, str | None]:
    """Parse a streaming line into (human_readable_message, final_result).

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

    parsers = {
        "claude_stream_json": _parse_claude_stream_json_line,
        "gemini_stream_json": _parse_gemini_stream_json_line,
        "codex_jsonl": _parse_codex_jsonl_line,
    }
    parser = parsers.get(parser_name)
    if parser is None:
        return (line if line.strip() else None, None)
    return parser(data)


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
        """Build provider-specific streaming args."""
        args = self._build_args(prompt, workspace)
        streaming = self.config.streaming
        if not streaming or streaming.mode != "output_format_swap":
            return args

        for i in range(1, len(args)):
            if args[i - 1] == streaming.flag and args[i] == streaming.from_value:
                args[i] = streaming.to_value
                args.extend(streaming.extra_args)
                break
        return args

    def _is_stream_json_args(self, args: list[str]) -> bool:
        """Check whether the built args produce stream-json output."""
        streaming = self.config.streaming
        if not streaming or streaming.mode != "output_format_swap":
            return False

        for i in range(1, len(args)):
            if args[i - 1] == streaming.flag and args[i] == streaming.to_value:
                return True
        return False

    def _should_parse_stream_output(self, args: list[str]) -> bool:
        """Check whether stdout should be interpreted by a structured parser."""
        if self.config.stream_parser == "plain_text":
            return False
        if self.config.stream_parser == "codex_jsonl":
            return "--json" in args
        return self._is_stream_json_args(args)

    async def execute(
        self,
        prompt: str,
        workspace: str | None = None,
        timeout: int | None = None,
        raw_output: bool = False,
    ) -> str:
        """Execute a prompt and return the full output."""
        args = self._build_args(prompt, workspace)
        if raw_output:
            filtered = []
            skip_next = False
            for arg in args:
                if skip_next:
                    skip_next = False
                    continue
                if arg == "--output-format":
                    skip_next = True
                    continue
                filtered.append(arg)
            args = filtered
        effective_timeout = timeout or self.config.timeout

        proc = await asyncio.create_subprocess_exec(
            self.config.command,
            *args,
            cwd=workspace,
            env=self._clean_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=10 * 1024 * 1024,
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
        should_parse_stream = self._should_parse_stream_output(args)
        effective_timeout = timeout or self.config.timeout

        # Use a 10 MB read buffer — the default 64 KB is too small for agents
        # that produce large outputs (e.g. multi-document analysis reports).
        _STREAM_LIMIT = 10 * 1024 * 1024
        proc = await asyncio.create_subprocess_exec(
            self.config.command,
            *args,
            cwd=workspace,
            env=self._clean_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=_STREAM_LIMIT,
            start_new_session=True,
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

                    if should_parse_stream:
                        msg, result = parse_stream_json_line(
                            text,
                            parser_name=self.config.stream_parser,
                        )
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
            # Kill the entire process group so computer use children (MCP desktop
            # automation processes) are also terminated — not just the direct child.
            if proc.returncode is None:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass
                await proc.wait()


def build_agent_prompt(agent: dict, inputs: dict, run_id: str = "") -> str:
    """Build the prompt to send to the CLI provider.

    If the agent has a forge_path, instructs the tool to read and follow
    the agentic.md. Otherwise falls back to description-based prompting.
    When run_id is provided, outputs are isolated to output/{run_id}/.
    """
    parts = []

    forge_path = agent.get("forge_path", "")
    output_dir = f"output/{run_id}" if run_id else "output"

    if forge_path:
        parts.append(
            f"Read {forge_path}/agentic.md and execute the workflow defined there."
        )
        if run_id:
            parts.append(
                f"\nIMPORTANT: Save all outputs to {forge_path}/{output_dir}/ "
                f"instead of {forge_path}/output/. This isolates this run's outputs. "
                f"Runtime input artifacts are available under {forge_path}/{output_dir}/inputs/. "
                f"Agent outputs go to {forge_path}/{output_dir}/agent_outputs/. "
                f"User outputs go to {forge_path}/{output_dir}/user_outputs/."
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
            parts.append(f"  {key}: {_format_input_value(value)}")

    output_schema = agent.get("output_schema", [])
    if output_schema:
        field_names = [f["name"] for f in output_schema]
        parts.append(
            f"\nReturn ONLY a JSON object with these fields: {', '.join(field_names)}"
        )
        file_like_fields = [
            field["name"] for field in output_schema
            if field.get("type") in {"file", "archive", "directory"}
        ]
        if file_like_fields:
            parts.append(
                "For file, archive, or directory outputs, return an object with "
                "`kind`, `path`, `filename`, and `mime_type` instead of a plain string path. "
                "The `path` must point to a file or directory inside the run's user_outputs folder."
            )
        parts.append("No explanation, no markdown -- just the JSON.")

    return "\n".join(parts)


def _kebab_case(name: str) -> str:
    """Convert a step name to kebab-case for step file lookup."""
    return name.lower().replace(" ", "-").replace("_", "-")


def build_step_prompt(
    agent: dict, inputs: dict, step_number: int, step: dict, run_id: str = "",
) -> str:
    """Build a prompt for a single workflow step.

    Instructs the CLI to read agentic.md and execute ONLY the given step.
    Detects step file architecture (agent/steps/) and references step files
    when available. Falls back to old monolithic format for backward compat.
    Previous steps' output files are already on disk so the agent can read them.
    When run_id is provided, outputs are isolated to output/{run_id}/.
    """
    forge_path = agent.get("forge_path", "")
    step_name = step["name"] if isinstance(step, dict) else step
    uses_cu = step.get("computer_use", False) if isinstance(step, dict) else False
    output_dir = f"output/{run_id}" if run_id else "output"

    parts = []

    if forge_path:
        # Detect new step file architecture
        step_kebab = _kebab_case(step_name)
        step_file = f"{forge_path}/agent/steps/step_{step_number:02d}_{step_kebab}.md"
        has_step_files = os.path.isdir(
            os.path.join(_PROJECT_ROOT, forge_path, "agent", "steps")
        )

        parts.append(
            f"Read {forge_path}/agentic.md for the full workflow context."
        )

        if has_step_files:
            parts.append(
                f"\nRead {step_file} for the detailed step instructions."
            )
            parts.append(
                f"\nExecute ONLY Step {step_number}: {step_name}."
            )
            parts.append(
                "Follow the step file instructions exactly. "
                "Previous steps have already run and their output files "
                f"(in {output_dir}/agent_outputs/) are on disk -- read them as needed."
            )
            parts.append(
                f"Runtime input artifacts are available under {forge_path}/{output_dir}/inputs/."
            )
            parts.append(
                f"Save your agent output to {forge_path}/{output_dir}/agent_outputs/"
                f"step_{step_number:02d}_agent_output.md"
            )
            parts.append(
                f"Save any user-facing deliverables to {forge_path}/{output_dir}/user_outputs/"
                f"step_{step_number:02d}/"
            )
        else:
            # Old monolithic format -- no step files
            parts.append(
                f"\nExecute ONLY Step {step_number}: {step_name}."
            )
            parts.append(
                "Do NOT execute any other steps. Previous steps have already run "
                "and their output files are on disk -- read them as needed."
            )
    else:
        parts.append(f"You are an agent named '{agent['name']}'.")
        if agent.get("description"):
            parts.append(f"Your goal: {agent['description']}")
        parts.append(f"\nExecute this task: {step_name}")

    if uses_cu:
        parts.append(
            "\nThis step requires desktop automation: use the computer_use MCP "
            "tools (screenshot, click, type_text, key_press) to interact with "
            "the screen. Open applications, navigate visually, and capture "
            "information by reading screenshots. Do NOT use web_fetch or curl."
        )

    if inputs:
        parts.append("\nInputs:")
        for key, value in inputs.items():
            parts.append(f"  {key}: {_format_input_value(value)}")

    # Only request JSON output on the last step
    steps = agent.get("steps", [])
    is_last = step_number == len(steps)
    output_schema = agent.get("output_schema", [])
    if is_last and output_schema:
        field_names = [f["name"] for f in output_schema]
        parts.append(
            f"\nReturn ONLY a JSON object with these fields: {', '.join(field_names)}"
        )
        file_like_fields = [
            field["name"] for field in output_schema
            if field.get("type") in {"file", "archive", "directory"}
        ]
        if file_like_fields:
            parts.append(
                "For file, archive, or directory outputs, return an object with "
                "`kind`, `path`, `filename`, and `mime_type` instead of a plain string path. "
                "The `path` must point to a file or directory inside the run's user_outputs folder."
            )
        parts.append("No explanation, no markdown -- just the JSON.")

    return "\n".join(parts)


def _format_input_value(value: object) -> str:
    if isinstance(value, dict) and value.get("kind") in {"file", "archive", "directory"}:
        filename = value.get("filename", "")
        path = value.get("path", "")
        kind = value.get("kind", "file")
        return f"{kind}('{filename}' at '{path}')"
    return str(value)

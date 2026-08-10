"""Config-driven agent providers. One executor class, multiple backends via config.

Provider definitions live in providers.yaml at the project root -- adding a new provider
means editing that YAML file, zero code changes.
"""

import asyncio
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator

from api.utils.platform import (
    kill_process_tree,
    new_session_kwargs,
    remove_path_entry,
    resolve_command,
    venv_bin_dir,
)

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
    """Event emitted during agent execution.

    ``data`` is a string for the text-shaped types (``output``, ``error``,
    ``done``, ``awaiting``) and structured for the ones that carry a payload
    (``todos``). It was annotated ``str``, so the bridge coerced the checklist
    with ``str()`` and the phone received a Python repr - single-quoted, and not
    parseable as JSON by anything on the other end.
    """
    type: str  # "output", "error", "done", "todos", "awaiting"
    data: str | list | dict = ""


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
    """Configuration for an agent provider.

    ``command`` defaults to empty because a **native** provider has none: it is
    the in-process engine, named by a `module` in `providers.yaml` rather than
    an argv. Before 0.4.1 this field was required, so loading a native entry
    raised and every agent created on one went to status `error` - the native
    path was unreachable through the API while every unit test passed.
    """
    name: str
    command: str = ""
    args: list[str] = field(default_factory=list)
    available_check: list[str] = field(default_factory=list)
    timeout: int = 300
    streaming: StreamingConfig | None = None
    stream_parser: str = "plain_text"


def _load_providers_doc() -> dict:
    """The whole of providers.yaml, including its top-level keys."""
    yaml_path = Path(__file__).resolve().parent.parent.parent / "providers.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(
            f"Provider config not found at {yaml_path}. "
            "Create api/providers.yaml with provider definitions."
        )
    with open(yaml_path) as f:
        return yaml.safe_load(f) or {}


def _load_providers_yaml() -> dict[str, dict]:
    """Load provider configs from providers.yaml at the project root."""
    return _load_providers_doc().get("providers", {})


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
        # A native provider is the in-process engine: it has a `module`, not a
        # `command` and `args`, so there is no argv to append a --model flag to.
        # The model reaches it as a field instead (see `build_native_provider`).
        # Before 0.4.1 this raised KeyError and every agent on a native provider
        # went to status `error` at creation, which made the whole native path
        # unreachable through the API.
        config["args"] = [*config.get("args", []), "--model", model]
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


async def machine_default_provider() -> str:
    """The provider a run that named none executes on.

    `providers.yaml` is the machine's configuration, and its top-level
    `default_provider` is the machine's answer. When it names nothing, or names
    something no longer in the file, the fallback is the first provider on the
    machine that answers as available, so a run still starts rather than failing
    on a stale config line.
    """
    doc = _load_providers_doc()
    providers = doc.get("providers") or {}
    configured = doc.get("default_provider")
    if configured and configured in providers:
        return configured

    for key in providers:
        provider = CLIAgentProvider(load_provider_config(key))
        if await provider.is_available():
            return key

    raise RuntimeError(
        "No provider is available. Configure one in providers.yaml and set "
        "default_provider."
    )


def machine_default_model(provider_key: str) -> str | None:
    """The model that provider runs by default, or ``None`` to let the provider
    choose its own."""
    entry = (_load_providers_doc().get("providers") or {}).get(provider_key) or {}
    return entry.get("default_model")


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
        """Check if the CLI tool is installed.

        A provider with no `command` is the in-process engine, which is always
        available: there is nothing to find on PATH and nothing to spawn.
        Without this the empty argv reached `create_subprocess_exec` and raised
        PermissionError on an empty string, which is what put every agent on a
        native provider into status `error` at creation.
        """
        if not self.config.command and not self.config.available_check:
            return True
        if not self.config.available_check:
            return shutil.which(self.config.command) is not None
        try:
            resolved_check = [resolve_command(self.config.available_check[0])] + self.config.available_check[1:]
            proc = await asyncio.create_subprocess_exec(
                *resolved_check,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            return proc.returncode == 0
        except (FileNotFoundError, PermissionError, OSError):
            return False

    @staticmethod
    def _clean_env() -> dict[str, str]:
        """Build a subprocess environment without session-nesting or venv vars.

        Strips CLAUDE* env vars (prevent nesting detection) and removes the
        active virtualenv from PATH so bare 'python3' resolves to the system
        Python, not the API's venv.
        """
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("CLAUDE")}
        # Strip active venv from PATH (handles both bin/ and Scripts/)
        venv = env.pop("VIRTUAL_ENV", None)
        if venv:
            env["PATH"] = remove_path_entry(
                env.get("PATH", ""), str(venv_bin_dir(venv))
            )
        return env

    @classmethod
    def _computer_use_env(cls) -> dict[str, str]:
        """Build env for desktop steps with computer_use venv on PATH.

        Prepends computer_use/.venv/bin so that 'python3' resolves to the
        venv that has mcp/fastmcp installed, ensuring the MCP server starts.
        """
        env = cls._clean_env()
        cu_venv_bin = str(venv_bin_dir(
            os.path.join(_PROJECT_ROOT, "computer_use", ".venv")
        ))
        env["PATH"] = os.pathsep.join([cu_venv_bin, env.get("PATH", "")])
        return env

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
        computer_use: bool = False,
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

        env = self._computer_use_env() if computer_use else self._clean_env()
        proc = await asyncio.create_subprocess_exec(
            resolve_command(self.config.command),
            *args,
            cwd=workspace,
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
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
        computer_use: bool = False,
        **_: object,   # run_id: the native path needs it, a subprocess does not
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

        # Use a 10 MB read buffer - the default 64 KB is too small for agents
        # that produce large outputs (e.g. multi-document analysis reports).
        _STREAM_LIMIT = 10 * 1024 * 1024
        env = self._computer_use_env() if computer_use else self._clean_env()
        proc = await asyncio.create_subprocess_exec(
            resolve_command(self.config.command),
            *args,
            cwd=workspace,
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=_STREAM_LIMIT,
            **new_session_kwargs(),
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
                            break  # Claude is done; stop reading -- child processes may hold pipe open
                        elif msg is not None:
                            collected.append(msg)
                            yield ExecutionEvent(type="output", data=msg)
                    else:
                        collected.append(text)
                        yield ExecutionEvent(type="output", data=text)

                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    await kill_process_tree(proc)
                # If we got a result event, the step succeeded -- ignore exit code
                # (process may have been killed to clean up orphan children)
                if final_result is not None:
                    yield ExecutionEvent(type="done", data=final_result)
                elif proc.returncode not in (None, 0):
                    stderr_data = await proc.stderr.read()
                    error_msg = stderr_data.decode().strip() if stderr_data else "Unknown error"
                    yield ExecutionEvent(type="error", data=error_msg)
                else:
                    yield ExecutionEvent(type="done", data="\n".join(collected))

            async for event in read_stream():
                yield event

        except asyncio.TimeoutError:
            yield ExecutionEvent(type="error", data=f"Timed out after {effective_timeout}s")
        finally:
            # Always ensure the subprocess is killed and reaped, even if the
            # caller stops iterating, an exception is raised, or the run fails.
            # Kill the entire process tree so computer use children (MCP desktop
            # automation processes) are also terminated - not just the direct child.
            if proc.returncode is None:
                await kill_process_tree(proc)


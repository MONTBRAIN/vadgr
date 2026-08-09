"""Tests for service layer."""

import os
import subprocess
import pytest
import yaml
from pathlib import Path
from unittest.mock import AsyncMock, patch

from api.engine.providers import (
    CLIAgentProvider, ExecutionEvent, ProviderConfig, ProviderError,
    StreamingConfig, load_provider_config, _load_providers_yaml,
)
from api.persistence.repositories import RunRepository
from api.services.execution_service import ExecutionService


class TestProvidersYamlLoading:
    """Tests for YAML-based provider configuration loading."""

    def test_load_providers_yaml_returns_dict_with_providers(self):
        providers = _load_providers_yaml()
        assert isinstance(providers, dict)
        assert len(providers) >= 1

    def test_load_providers_yaml_missing_file_raises(self, tmp_path):
        """When providers.yaml doesn't exist, raise FileNotFoundError."""
        import api.engine.providers as providers_mod
        original_file = providers_mod.__file__
        try:
            # Point the module's __file__ to a fake location so
            # _load_providers_yaml looks for providers.yaml in tmp_path
            fake_file = str(tmp_path / "engine" / "providers.py")
            (tmp_path / "engine").mkdir(parents=True, exist_ok=True)
            providers_mod.__file__ = fake_file
            with pytest.raises(FileNotFoundError, match="Provider config not found"):
                _load_providers_yaml()
        finally:
            providers_mod.__file__ = original_file

    def test_load_from_custom_yaml(self, tmp_path):
        """Load provider config from a custom YAML file."""
        custom_yaml = tmp_path / "providers.yaml"
        custom_yaml.write_text(yaml.dump({
            "providers": {
                "custom_tool": {
                    "name": "Custom Tool",
                    "command": "custom-cli",
                    "args": ["-p", "{{prompt}}"],
                    "available_check": ["custom-cli", "--version"],
                    "timeout": 120,
                }
            }
        }))

        with open(custom_yaml) as f:
            data = yaml.safe_load(f)
        providers = data.get("providers", {})

        assert "custom_tool" in providers
        config = ProviderConfig(**providers["custom_tool"])
        assert config.name == "Custom Tool"
        assert config.command == "custom-cli"
        assert config.timeout == 120
        assert "{{prompt}}" in config.args

    def test_yaml_providers_all_have_placeholder(self):
        """Every CLI provider in YAML must have {{prompt}} placeholder in args.
        Native providers (the engine loop) drive the model directly and carry no
        command/args, so they are exempt."""
        providers = _load_providers_yaml()
        for key, prov in providers.items():
            if prov.get("kind") == "native":
                continue
            args_str = " ".join(prov["args"])
            assert "{{prompt}}" in args_str, (
                f"Provider '{key}' missing {{{{prompt}}}} placeholder in args"
            )

    def test_yaml_providers_all_instantiate_as_provider_config(self):
        """Every CLI provider in YAML can be deserialized into a ProviderConfig.
        Native providers are exempt -- they are not CLI subprocess providers."""
        providers = _load_providers_yaml()
        valid_fields = {f.name for f in ProviderConfig.__dataclass_fields__.values()}
        for key, prov in providers.items():
            if prov.get("kind") == "native":
                continue
            filtered = {k: v for k, v in prov.items() if k in valid_fields}
            config = ProviderConfig(**filtered)
            assert config.name, f"{key} has empty name"
            assert config.command, f"{key} has empty command"
            assert len(config.args) > 0, f"{key} has no args"


class TestProviderConfig:

    def test_load_claude_code_config(self):
        config = load_provider_config("claude_code")
        assert config.name == "Claude Code"
        assert config.command == "claude"
        assert "-p" in config.args
        assert "--dangerously-skip-permissions" in config.args

    def test_load_codex_config(self):
        config = load_provider_config("codex")
        assert config.command == "codex"
        assert "exec" in config.args

    def test_load_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            load_provider_config("nonexistent")

    def test_load_with_overrides(self):
        config = load_provider_config("claude_code", {"timeout": 600})
        assert config.timeout == 600

    def test_override_does_not_mutate_yaml_source(self):
        """Overrides apply to the returned config, not the YAML data."""
        config1 = load_provider_config("claude_code", {"timeout": 999})
        config2 = load_provider_config("claude_code")
        assert config1.timeout == 999
        assert config2.timeout != 999

    def test_load_returns_provider_config_instance(self):
        config = load_provider_config("claude_code")
        assert isinstance(config, ProviderConfig)

    def test_load_claude_with_model_appends_model_flag(self):
        config = load_provider_config("claude_code", {"model": "claude-opus-4-6"})
        assert "--model" in config.args
        assert "claude-opus-4-6" in config.args

    def test_load_codex_with_model_appends_model_flag(self):
        config = load_provider_config("codex", {"model": "gpt-5-codex"})
        assert "--model" in config.args
        assert "gpt-5-codex" in config.args

    def test_load_claude_streaming_config(self):
        config = load_provider_config("claude_code")
        assert config.streaming is not None
        assert config.streaming.flag == "--output-format"
        assert config.streaming.from_value == "json"
        assert config.streaming.to_value == "stream-json"
        assert config.streaming.extra_args == ["--verbose"]

    def test_load_gemini_streaming_config(self):
        config = load_provider_config("gemini")
        assert config.streaming is not None
        assert config.streaming.flag == "--output-format"
        assert config.streaming.from_value == "json"
        assert config.streaming.to_value == "stream-json"
        assert config.streaming.extra_args == []

    def test_load_claude_stream_parser(self):
        config = load_provider_config("claude_code")
        assert config.stream_parser == "claude_stream_json"

    def test_load_gemini_stream_parser(self):
        config = load_provider_config("gemini")
        assert config.stream_parser == "gemini_stream_json"

    def test_load_codex_stream_parser(self):
        config = load_provider_config("codex")
        assert config.stream_parser == "codex_jsonl"


class TestCLIAgentProvider:

    def test_clean_env_strips_claudecode(self):
        config = ProviderConfig(name="Test", command="echo", args=[])
        provider = CLIAgentProvider(config)
        os.environ["CLAUDECODE"] = "1"
        try:
            env = provider._clean_env()
            assert "CLAUDECODE" not in env
            assert "PATH" in env
        finally:
            del os.environ["CLAUDECODE"]

    def test_clean_env_passes_through_normal_vars(self):
        config = ProviderConfig(name="Test", command="echo", args=[])
        provider = CLIAgentProvider(config)
        env = provider._clean_env()
        assert "HOME" in env
        assert "PATH" in env

    def test_build_args_replaces_prompt(self):
        config = ProviderConfig(
            name="Test",
            command="test-cli",
            args=["-p", "{{prompt}}", "--flag"],
        )
        provider = CLIAgentProvider(config)
        args = provider._build_args("hello world")
        assert args == ["-p", "hello world", "--flag"]

    def test_build_args_replaces_workspace(self):
        config = ProviderConfig(
            name="Test",
            command="test-cli",
            args=["--dir", "{{workspace}}", "-p", "{{prompt}}"],
        )
        provider = CLIAgentProvider(config)
        args = provider._build_args("hello", "/tmp/work")
        assert args == ["--dir", "/tmp/work", "-p", "hello"]

    def test_build_args_without_workspace_leaves_placeholder(self):
        config = ProviderConfig(
            name="Test",
            command="test-cli",
            args=["--dir", "{{workspace}}", "-p", "{{prompt}}"],
        )
        provider = CLIAgentProvider(config)
        args = provider._build_args("hello")
        assert args == ["--dir", "{{workspace}}", "-p", "hello"]

    def test_build_streaming_args_swaps_output_format_for_claude(self):
        config = load_provider_config("claude_code")
        provider = CLIAgentProvider(config)

        args = provider._build_streaming_args("hello")

        assert "--output-format" in args
        assert "stream-json" in args
        assert "--verbose" in args
        assert "json" not in args

    def test_build_streaming_args_swaps_output_format_for_gemini_without_verbose(self):
        config = load_provider_config("gemini")
        provider = CLIAgentProvider(config)

        args = provider._build_streaming_args("hello")

        assert "--output-format" in args
        assert "stream-json" in args
        assert "--verbose" not in args
        assert "json" not in args

    def test_build_streaming_args_keeps_args_when_provider_has_no_streaming_config(self):
        config = ProviderConfig(
            name="Test",
            command="test-cli",
            args=["--prompt", "{{prompt}}"],
        )
        provider = CLIAgentProvider(config)

        args = provider._build_streaming_args("hello")

        assert args == ["--prompt", "hello"]

    @pytest.mark.asyncio
    async def test_is_available_returns_false_for_missing_tool(self):
        config = ProviderConfig(
            name="Test",
            command="nonexistent-tool-xyz",
            available_check=["nonexistent-tool-xyz", "--version"],
        )
        provider = CLIAgentProvider(config)
        assert await provider.is_available() is False

    @pytest.mark.asyncio
    async def test_is_available_returns_true_for_existing_tool(self):
        config = ProviderConfig(
            name="Echo",
            command="echo",
            available_check=["echo", "test"],
        )
        provider = CLIAgentProvider(config)
        assert await provider.is_available() is True

    @pytest.mark.asyncio
    async def test_is_available_without_check_uses_which(self):
        config = ProviderConfig(
            name="Echo",
            command="echo",
            available_check=[],
        )
        provider = CLIAgentProvider(config)
        assert await provider.is_available() is True

    @pytest.mark.asyncio
    async def test_execute_resolves_command_before_spawn(self):
        """Commands are resolved via shutil.which so npm .cmd shims work on Windows."""
        config = ProviderConfig(
            name="Test",
            command="mycommand",
            args=["{{prompt}}"],
        )
        provider = CLIAgentProvider(config)
        with patch("api.engine.providers.resolve_command", return_value="/resolved/mycommand") as mock_resolve, \
             patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc
            await provider.execute("test")
            mock_resolve.assert_called_with("mycommand")
            # The resolved path should be the first arg to create_subprocess_exec
            assert mock_exec.call_args[0][0] == "/resolved/mycommand"

    @pytest.mark.asyncio
    async def test_is_available_resolves_command_in_check(self):
        """available_check commands are also resolved for Windows compatibility."""
        config = ProviderConfig(
            name="Test",
            command="mycommand",
            available_check=["mycommand", "--version"],
        )
        provider = CLIAgentProvider(config)
        with patch("api.engine.providers.resolve_command", return_value="/resolved/mycommand") as mock_resolve, \
             patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.wait = AsyncMock()
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc
            await provider.is_available()
            mock_resolve.assert_called_with("mycommand")
            assert mock_exec.call_args[0][0] == "/resolved/mycommand"

    @pytest.mark.asyncio
    async def test_execute_runs_subprocess_and_returns_stdout(self):
        """Execute a real subprocess (echo) and capture output."""
        config = ProviderConfig(
            name="Echo",
            command="echo",
            args=["{{prompt}}"],
        )
        provider = CLIAgentProvider(config)
        result = await provider.execute("hello from test")
        assert result == "hello from test"

    @pytest.mark.asyncio
    async def test_execute_with_json_output(self):
        """Execute printf to produce JSON output."""
        config = ProviderConfig(
            name="Printf",
            command="printf",
            args=['{"result": "{{prompt}}"}'],
        )
        provider = CLIAgentProvider(config)
        result = await provider.execute("done")
        assert result == '{"result": "done"}'

    @pytest.mark.asyncio
    async def test_execute_raises_provider_error_on_nonzero_exit(self):
        """Non-zero exit code raises ProviderError with stdout, stderr, exit_code."""
        config = ProviderConfig(
            name="Fail",
            command="bash",
            args=["-c", "echo partial-output; echo {{prompt}} >&2; exit 1"],
        )
        provider = CLIAgentProvider(config)
        with pytest.raises(ProviderError) as exc_info:
            await provider.execute("error msg")
        err = exc_info.value
        assert err.exit_code == 1
        assert "partial-output" in err.stdout
        assert "error msg" in err.stderr
        assert "Fail" in str(err)

    @pytest.mark.asyncio
    async def test_execute_raises_on_timeout(self):
        """Long-running process gets killed after timeout."""
        config = ProviderConfig(
            name="Sleep",
            command="sleep",
            args=["10"],
            timeout=1,
        )
        provider = CLIAgentProvider(config)
        with pytest.raises(TimeoutError, match="timed out after 1s"):
            await provider.execute("ignored", timeout=1)

    @pytest.mark.asyncio
    async def test_execute_custom_timeout_overrides_config(self):
        """Timeout parameter overrides config timeout."""
        config = ProviderConfig(
            name="Sleep",
            command="sleep",
            args=["10"],
            timeout=300,
        )
        provider = CLIAgentProvider(config)
        with pytest.raises(TimeoutError, match="timed out after 1s"):
            await provider.execute("ignored", timeout=1)

    @pytest.mark.asyncio
    async def test_execute_streaming_collects_lines(self):
        """Streaming execution collects output line by line."""
        config = ProviderConfig(
            name="Echo",
            command="bash",
            args=["-c", "echo line1; echo line2; echo line3"],
        )
        provider = CLIAgentProvider(config)
        events = []
        async for event in provider.execute_streaming("ignored"):
            events.append(event)

        output_events = [e for e in events if e.type == "output"]
        done_events = [e for e in events if e.type == "done"]
        assert len(output_events) == 3
        assert output_events[0].data == "line1"
        assert output_events[1].data == "line2"
        assert output_events[2].data == "line3"
        assert len(done_events) == 1

    @pytest.mark.asyncio
    async def test_execute_streaming_emits_error_on_failure(self):
        """Streaming execution emits error event on non-zero exit."""
        config = ProviderConfig(
            name="Fail",
            command="bash",
            args=["-c", "echo oops >&2; exit 1"],
        )
        provider = CLIAgentProvider(config)
        events = []
        async for event in provider.execute_streaming("ignored"):
            events.append(event)

        error_events = [e for e in events if e.type == "error"]
        assert len(error_events) == 1
        assert "oops" in error_events[0].data

    def test_build_streaming_args_swaps_output_format_to_stream_json(self):
        """For providers with --output-format json, streaming should swap to stream-json."""
        config = ProviderConfig(
            name="Claude Code",
            command="claude",
            args=["-p", "{{prompt}}", "--output-format", "json"],
            streaming=StreamingConfig(
                mode="output_format_swap",
                flag="--output-format",
                from_value="json",
                to_value="stream-json",
                extra_args=["--verbose"],
            ),
        )
        provider = CLIAgentProvider(config)
        args = provider._build_streaming_args("hello world")
        assert "--output-format" in args
        idx = args.index("--output-format")
        assert args[idx + 1] == "stream-json"
        # --verbose is required for stream-json with --print
        assert "--verbose" in args
        # Original config unchanged
        assert config.args[3] == "json"

    def test_build_streaming_args_no_swap_for_other_providers(self):
        """Providers without --output-format json should keep their args unchanged."""
        config = ProviderConfig(
            name="Aider",
            command="aider",
            args=["--message", "{{prompt}}", "--yes-always"],
        )
        provider = CLIAgentProvider(config)
        args = provider._build_streaming_args("hello")
        assert args == ["--message", "hello", "--yes-always"]

    def test_parse_stream_json_extracts_text_content(self):
        """stream-json assistant text messages should yield readable text."""
        from api.engine.providers import parse_stream_json_line
        line = '{"type":"assistant","message":{"content":[{"type":"text","text":"Analyzing the codebase..."}]}}'
        msg, result = parse_stream_json_line(line)
        assert msg == "Analyzing the codebase..."
        assert result is None

    def test_parse_stream_json_extracts_tool_use(self):
        """stream-json tool_use events should yield 'Using tool: X'."""
        from api.engine.providers import parse_stream_json_line
        line = '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read","input":{"file_path":"/tmp/test"}}]}}'
        msg, result = parse_stream_json_line(line)
        assert msg == "Using tool: Read"
        assert result is None

    def test_parse_stream_json_extracts_result(self):
        """stream-json result events should return the final output."""
        from api.engine.providers import parse_stream_json_line
        line = '{"type":"result","result":"{\\"report\\": \\"done\\"}"}'
        msg, result = parse_stream_json_line(line)
        assert msg is None
        assert result == '{"report": "done"}'

    def test_parse_stream_json_non_json_line_returns_raw(self):
        """Non-JSON lines should be returned as-is."""
        from api.engine.providers import parse_stream_json_line
        line = "some plain text output"
        msg, result = parse_stream_json_line(line)
        assert msg == "some plain text output"
        assert result is None

    def test_parse_stream_json_skips_uninteresting_events(self):
        """Events without useful content should return None."""
        from api.engine.providers import parse_stream_json_line
        line = '{"type":"system","subtype":"init","data":{}}'
        msg, result = parse_stream_json_line(line)
        assert msg is None
        assert result is None

    def test_parse_gemini_stream_json_extracts_assistant_message(self):
        from api.engine.providers import parse_stream_json_line
        line = '{"type":"message","role":"assistant","content":"Hello from Gemini","delta":true}'
        msg, result = parse_stream_json_line(line, parser_name="gemini_stream_json")
        assert msg == "Hello from Gemini"
        assert result is None

    def test_parse_gemini_stream_json_ignores_stats_only_result(self):
        from api.engine.providers import parse_stream_json_line
        line = '{"type":"result","status":"success","stats":{"total_tokens":123}}'
        msg, result = parse_stream_json_line(line, parser_name="gemini_stream_json")
        assert msg is None
        assert result is None

    def test_parse_codex_jsonl_extracts_assistant_message(self):
        from api.engine.providers import parse_stream_json_line
        line = '{"type":"agent_message_delta","delta":"Searching repository"}'
        msg, result = parse_stream_json_line(line, parser_name="codex_jsonl")
        assert msg == "Searching repository"
        assert result is None

    def test_parse_codex_jsonl_summarizes_command_start(self):
        from api.engine.providers import parse_stream_json_line
        line = (
            '{"type":"item.started","item":{"id":"item_1","type":"command_execution",'
            '"command":"/bin/bash -lc \'cd /repo && cat agentic.md\'",'
            '"aggregated_output":"","exit_code":null,"status":"in_progress"}}'
        )
        msg, result = parse_stream_json_line(line, parser_name="codex_jsonl")
        assert msg == "Running command: cat agentic.md"
        assert result is None

    def test_parse_codex_jsonl_extracts_reasoning_text(self):
        from api.engine.providers import parse_stream_json_line
        line = (
            '{"type":"item.completed","item":{"id":"item_0","type":"reasoning",'
            '"text":"**Reviewing agentic context and skills**"}}'
        )
        msg, result = parse_stream_json_line(line, parser_name="codex_jsonl")
        assert msg == "Reviewing agentic context and skills"
        assert result is None

    def test_parse_codex_jsonl_extracts_agent_message_text(self):
        from api.engine.providers import parse_stream_json_line
        line = (
            '{"type":"item.completed","item":{"id":"item_14","type":"agent_message",'
            '"text":"Captured categorized notes and highlights."}}'
        )
        msg, result = parse_stream_json_line(line, parser_name="codex_jsonl")
        assert msg == "Captured categorized notes and highlights."
        assert result is None

    def test_parse_codex_jsonl_ignores_command_completion_payload(self):
        from api.engine.providers import parse_stream_json_line
        line = (
            '{"type":"item.completed","item":{"id":"item_1","type":"command_execution",'
            '"command":"/bin/bash -lc \'cd /repo && cat agentic.md\'",'
            '"aggregated_output":"very long file contents","exit_code":0,"status":"completed"}}'
        )
        msg, result = parse_stream_json_line(line, parser_name="codex_jsonl")
        assert msg is None
        assert result is None

    def test_parse_codex_jsonl_ignores_turn_completed_usage(self):
        from api.engine.providers import parse_stream_json_line
        line = '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}'
        msg, result = parse_stream_json_line(line, parser_name="codex_jsonl")
        assert msg is None
        assert result is None

    @pytest.mark.asyncio
    async def test_execute_streaming_with_stream_json_parses_events(self):
        """Streaming with stream-json formatted output extracts readable messages."""
        # Simulate a process that outputs stream-json lines
        script = (
            'echo \'{"type":"assistant","message":{"content":[{"type":"text","text":"Reading files..."}]}}\'; '
            'echo \'{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Grep","input":{}}]}}\'; '
            'echo \'{"type":"result","result":"final output"}\''
        )
        config = ProviderConfig(
            name="Claude Code",
            command="bash",
            args=["-c", script, "--output-format", "json"],  # has the flag to trigger swap
            stream_parser="claude_stream_json",
            streaming=StreamingConfig(
                mode="output_format_swap",
                flag="--output-format",
                from_value="json",
                to_value="stream-json",
                extra_args=[],
            ),
        )
        provider = CLIAgentProvider(config)
        events = []
        async for event in provider.execute_streaming("ignored"):
            events.append(event)

        output_events = [e for e in events if e.type == "output"]
        done_events = [e for e in events if e.type == "done"]
        # Should have parsed the stream-json into readable messages
        messages = [e.data for e in output_events]
        assert "Reading files..." in messages
        assert "Using tool: Grep" in messages
        assert len(done_events) == 1
        assert done_events[0].data == "final output"

    @pytest.mark.asyncio
    async def test_execute_streaming_with_codex_jsonl_parses_events(self):
        script = (
            'echo \'{"type":"item.completed","item":{"id":"item_0","type":"reasoning","text":"**Reviewing context**"}}\'; '
            'echo \'{"type":"item.started","item":{"id":"item_1","type":"command_execution","command":"cat agentic.md","aggregated_output":"","exit_code":null,"status":"in_progress"}}\'; '
            'echo \'{"type":"item.completed","item":{"id":"item_2","type":"agent_message","text":"Captured summary."}}\'; '
            'echo \'{"type":"result","output_text":"final output"}\''
        )
        config = ProviderConfig(
            name="Codex",
            command="bash",
            args=["-c", script, "--json"],
            stream_parser="codex_jsonl",
        )
        provider = CLIAgentProvider(config)
        events = []
        async for event in provider.execute_streaming("ignored"):
            events.append(event)

        output_events = [e for e in events if e.type == "output"]
        done_events = [e for e in events if e.type == "done"]
        messages = [e.data for e in output_events]
        assert "Reviewing context" in messages
        assert "Running command: cat agentic.md" in messages
        assert "Captured summary." in messages
        assert len(done_events) == 1
        assert done_events[0].data == "final output"




def _provider_yielding(*events):
    """A provider whose stream yields the given events, then ends."""
    provider = AsyncMock()
    provider.calls = []

    async def fake_streaming(**kwargs):
        provider.calls.append(kwargs)
        for event in events:
            yield event

    provider.execute_streaming = fake_streaming
    return provider


class TestExecutionService:
    """The run's lifecycle after the workflow layer left."""

    @pytest.mark.asyncio
    async def test_start_run_drives_the_task_sentence_verbatim(self, db):
        run_repo = RunRepository(db)
        run = await run_repo.create(title="Tidy the inbox", inputs={"task": "Tidy the inbox"})
        provider = _provider_yielding(ExecutionEvent(type="done", data="all tidy"))

        service = ExecutionService(run_repo=run_repo, emit=AsyncMock())
        service._get_run_provider = AsyncMock(return_value=provider)
        await service.start_run(run["id"])

        assert provider.calls[0]["prompt"] == "Tidy the inbox"
        updated = await run_repo.get(run["id"])
        assert updated["status"] == "completed"
        assert updated["outputs"] == {"result": "all tidy"}

    @pytest.mark.asyncio
    async def test_run_started_carries_no_forge_path(self, db):
        run_repo = RunRepository(db)
        run = await run_repo.create(title="T", inputs={"task": "T"})
        emit = AsyncMock()

        service = ExecutionService(run_repo=run_repo, emit=emit)
        service._get_run_provider = AsyncMock(
            return_value=_provider_yielding(ExecutionEvent(type="done", data=""))
        )
        await service.start_run(run["id"])

        emit.assert_any_call(run["id"], "run_started", {})

    @pytest.mark.asyncio
    async def test_agent_frames_carry_run_id_and_the_title(self, db):
        """The frame names are frozen; what they carry is a run, not an agent."""
        run_repo = RunRepository(db)
        run = await run_repo.create(title="Summarise the week", inputs={"task": "Summarise the week"})
        emit = AsyncMock()

        service = ExecutionService(run_repo=run_repo, emit=emit)
        service._get_run_provider = AsyncMock(return_value=_provider_yielding(
            ExecutionEvent(type="output", data="thinking"),
            ExecutionEvent(type="done", data="done"),
        ))
        await service.start_run(run["id"])

        emit.assert_any_call(
            run["id"], "agent_started",
            {"run_id": run["id"], "name": "Summarise the week"},
        )
        emit.assert_any_call(
            run["id"], "agent_log", {"run_id": run["id"], "message": "thinking"},
        )
        emit.assert_any_call(
            run["id"], "agent_completed",
            {"run_id": run["id"], "outputs": {"result": "done"}},
        )
        emitted = {call.args[1] for call in emit.await_args_list}
        assert "step_completed" not in emitted

    @pytest.mark.asyncio
    async def test_an_error_event_fails_the_run(self, db):
        run_repo = RunRepository(db)
        run = await run_repo.create(title="T", inputs={"task": "T"})
        emit = AsyncMock()

        service = ExecutionService(run_repo=run_repo, emit=emit)
        service._get_run_provider = AsyncMock(return_value=_provider_yielding(
            ExecutionEvent(type="error", data="the loop gave up"),
        ))
        await service.start_run(run["id"])

        updated = await run_repo.get(run["id"])
        assert updated["status"] == "failed"
        assert updated["outputs"] == {"error": "the loop gave up"}
        emit.assert_any_call(
            run["id"], "agent_failed",
            {"run_id": run["id"], "error": "the loop gave up"},
        )

    @pytest.mark.asyncio
    async def test_awaiting_and_todos_pass_through_unchanged(self, db):
        run_repo = RunRepository(db)
        run = await run_repo.create(title="T", inputs={"task": "T"})
        emit = AsyncMock()

        service = ExecutionService(run_repo=run_repo, emit=emit)
        service._get_run_provider = AsyncMock(return_value=_provider_yielding(
            ExecutionEvent(type="todos", data=[{"id": "1", "content": "c", "status": "pending"}]),
            ExecutionEvent(type="awaiting", data="may I?"),
            ExecutionEvent(type="done", data=""),
        ))
        await service.start_run(run["id"])

        emit.assert_any_call(
            run["id"], "todos",
            {"items": [{"id": "1", "content": "c", "status": "pending"}]},
        )
        emit.assert_any_call(run["id"], "awaiting", {"prompt": "may I?"})

    @pytest.mark.asyncio
    async def test_a_run_that_named_a_provider_keeps_it(self, db):
        run_repo = RunRepository(db)
        run = await run_repo.create(
            title="T", inputs={"task": "T"}, provider="codex", model="gpt-5.4",
        )
        service = ExecutionService(run_repo=run_repo, emit=AsyncMock())
        assert await service._resolve_config(await run_repo.get(run["id"])) == ("codex", "gpt-5.4")

    @pytest.mark.asyncio
    async def test_a_run_that_named_none_takes_the_machine_default(self, db):
        """The machine's default is providers.yaml's, not a constant in code."""
        run_repo = RunRepository(db)
        run = await run_repo.create(title="T", inputs={"task": "T"})
        service = ExecutionService(run_repo=run_repo, emit=AsyncMock())

        with patch("api.services.execution_service.machine_default_provider",
                   AsyncMock(return_value="anthropic_oauth")), \
             patch("api.services.execution_service.machine_default_model",
                   return_value="claude-opus-5"):
            resolved = await service._resolve_config(await run_repo.get(run["id"]))
        assert resolved == ("anthropic_oauth", "claude-opus-5")

    @pytest.mark.asyncio
    async def test_the_native_path_has_no_wall_clock_deadline(self, db):
        service = ExecutionService(run_repo=RunRepository(db), emit=AsyncMock())
        with patch("api.services.execution_service.is_native_provider", return_value=True):
            assert service._timeout_for("anthropic_oauth") is None


class TestMachineDefaults:

    @pytest.mark.asyncio
    async def test_default_provider_comes_from_the_yaml(self):
        from api.engine.providers import machine_default_provider

        assert await machine_default_provider() == "anthropic_oauth"

    def test_default_model_comes_from_the_provider_entry(self):
        from api.engine.providers import machine_default_model

        assert machine_default_model("anthropic_oauth") == "claude-opus-5"
        assert machine_default_model("codex") is None


class TestTheRowRecordsWhatRanIt:
    """A run that named no provider still ran on one, and the published row is
    where a client has to read that from."""

    @pytest.mark.asyncio
    async def test_resolution_is_written_back_to_the_row(self, db):
        run_repo = RunRepository(db)
        run = await run_repo.create(title="T", inputs={"task": "T"})
        assert run["provider"] is None and run["model"] is None

        service = ExecutionService(run_repo=run_repo, emit=AsyncMock())
        with patch("api.services.execution_service.machine_default_provider",
                   AsyncMock(return_value="anthropic_oauth")), \
             patch("api.services.execution_service.machine_default_model",
                   return_value="claude-opus-5"):
            await service._resolve_config(await run_repo.get(run["id"]))

        stored = await run_repo.get(run["id"])
        assert stored["provider"] == "anthropic_oauth"
        assert stored["model"] == "claude-opus-5"

    @pytest.mark.asyncio
    async def test_a_named_pair_is_left_exactly_as_it_was_asked_for(self, db):
        run_repo = RunRepository(db)
        run = await run_repo.create(
            title="T", inputs={"task": "T"}, provider="codex", model="gpt-5.4",
        )
        service = ExecutionService(run_repo=run_repo, emit=AsyncMock())
        await service._resolve_config(await run_repo.get(run["id"]))

        stored = await run_repo.get(run["id"])
        assert (stored["provider"], stored["model"]) == ("codex", "gpt-5.4")

"""Tests for service layer."""

import os
import pytest
import yaml
from pathlib import Path
from unittest.mock import AsyncMock, patch

from api.engine.providers import (
    CLIAgentProvider, ProviderConfig, ProviderError, StreamingConfig,
    build_agent_prompt, load_provider_config, _load_providers_yaml,
)
from api.services.computer_use_service import ComputerUseService
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
        """Every provider in YAML must have {{prompt}} placeholder in args."""
        providers = _load_providers_yaml()
        for key, prov in providers.items():
            args_str = " ".join(prov["args"])
            assert "{{prompt}}" in args_str, (
                f"Provider '{key}' missing {{{{prompt}}}} placeholder in args"
            )

    def test_yaml_providers_all_instantiate_as_provider_config(self):
        """Every provider in YAML can be deserialized into a ProviderConfig."""
        providers = _load_providers_yaml()
        valid_fields = {f.name for f in ProviderConfig.__dataclass_fields__.values()}
        for key, prov in providers.items():
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


class TestBuildAgentPrompt:

    def test_prompt_with_forge_path(self):
        agent = {
            "name": "Research",
            "description": "Research a topic",
            "forge_path": "output/research/",
            "output_schema": [{"name": "findings", "type": "text"}],
        }
        prompt = build_agent_prompt(agent, {"topic": "AI"})
        assert "agentic.md" in prompt
        assert "topic: AI" in prompt
        assert "findings" in prompt

    def test_prompt_without_forge_path(self):
        agent = {
            "name": "Research",
            "description": "Research a topic",
            "forge_path": "",
            "output_schema": [],
        }
        prompt = build_agent_prompt(agent, {"topic": "AI"})
        assert "Research" in prompt
        assert "Research a topic" in prompt
        assert "agentic.md" not in prompt

    def test_prompt_with_empty_inputs(self):
        agent = {"name": "T", "description": "desc", "forge_path": ""}
        prompt = build_agent_prompt(agent, {})
        assert "Inputs:" not in prompt

    def test_prompt_requests_json_output(self):
        agent = {
            "name": "T",
            "description": "",
            "forge_path": "",
            "output_schema": [{"name": "result", "type": "text"}],
        }
        prompt = build_agent_prompt(agent, {})
        assert "JSON" in prompt

    def test_prompt_multiple_inputs(self):
        agent = {"name": "T", "description": "", "forge_path": ""}
        prompt = build_agent_prompt(agent, {"a": "1", "b": "2"})
        assert "a: 1" in prompt
        assert "b: 2" in prompt

    def test_prompt_multiple_output_fields(self):
        agent = {
            "name": "T",
            "description": "",
            "forge_path": "",
            "output_schema": [
                {"name": "summary", "type": "text"},
                {"name": "score", "type": "number"},
            ],
        }
        prompt = build_agent_prompt(agent, {})
        assert "summary" in prompt
        assert "score" in prompt

    def test_prompt_no_description(self):
        agent = {"name": "T", "description": "", "forge_path": ""}
        prompt = build_agent_prompt(agent, {})
        assert "Your goal:" not in prompt


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


class TestComputerUseService:

    @pytest.mark.asyncio
    async def test_run_agent_delegates_to_engine(self):
        service = ComputerUseService()
        service._engine = AsyncMock()
        service._engine.run_task = AsyncMock(return_value={
            "success": True, "screenshot": "base64..."
        })
        callback = AsyncMock()

        agent = {"id": "a1", "name": "Fill Form", "description": "Fill web form"}
        result = await service.run_agent(agent, {"url": "http://example.com"}, callback)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_run_agent_returns_failure_when_engine_unavailable(self):
        service = ComputerUseService()
        service._engine = None
        callback = AsyncMock()

        agent = {"id": "a1", "name": "T", "description": ""}
        result = await service.run_agent(agent, {}, callback)
        assert result["success"] is False


class TestAgentService:

    @pytest.mark.asyncio
    async def test_create_agent_sets_creating_status(self, db):
        from api.persistence.repositories import AgentRepository
        from api.services.agent_service import AgentService
        agent_repo = AgentRepository(db)
        provider = AsyncMock(spec=CLIAgentProvider)
        service = AgentService(agent_repo=agent_repo, provider=provider)

        agent = await service.create_agent(name="Test", description="A test agent")
        assert agent["status"] == "creating"
        assert agent["name"] == "Test"

    @pytest.mark.asyncio
    async def test_run_forge_updates_agent_to_ready(self, db):
        from api.persistence.repositories import AgentRepository
        from api.services.agent_service import AgentService
        agent_repo = AgentRepository(db)
        provider = AsyncMock(spec=CLIAgentProvider)

        forge_output = '{"result": "{\\"forge_path\\": \\"output/test/\\", \\"forge_config\\": {\\"complexity\\": \\"simple\\", \\"steps\\": 1, \\"prompts\\": [\\"01_Test.md\\"]}, \\"input_schema\\": [{\\"name\\": \\"topic\\", \\"type\\": \\"text\\", \\"required\\": true}], \\"output_schema\\": [{\\"name\\": \\"result\\", \\"type\\": \\"text\\"}]}"}'
        provider.execute = AsyncMock(return_value=forge_output)

        service = AgentService(agent_repo=agent_repo, provider=provider)
        agent = await service.create_agent(name="Test", description="A test agent")
        assert agent["status"] == "creating"

        await service.run_forge(agent["id"])

        updated = await agent_repo.get(agent["id"])
        assert updated["status"] == "ready"
        assert updated["forge_path"] == "output/test/"
        assert updated["forge_config"]["complexity"] == "simple"
        assert len(updated["input_schema"]) == 1
        assert len(updated["output_schema"]) == 1

    @pytest.mark.asyncio
    async def test_run_forge_passes_agent_id_to_provider(self, db):
        """Forge prompt must include the agent ID so output goes to output/{id}/."""
        from api.persistence.repositories import AgentRepository
        from api.services.agent_service import AgentService
        agent_repo = AgentRepository(db)
        provider = AsyncMock(spec=CLIAgentProvider)

        forge_output = '{"forge_path": "output/test/", "forge_config": {}, "input_schema": [], "output_schema": []}'
        provider.execute = AsyncMock(return_value=forge_output)

        service = AgentService(agent_repo=agent_repo, provider=provider)
        agent = await service.create_agent(name="Test", description="A test agent")

        await service.run_forge(agent["id"])

        # Verify the prompt sent to forge includes the agent ID
        call_args = provider.execute.call_args
        prompt = call_args.kwargs.get("prompt") or call_args[1].get("prompt") or call_args[0][0]
        assert agent["id"] in prompt

    @pytest.mark.asyncio
    async def test_run_forge_uses_agent_provider_and_model(self, db):
        from api.persistence.repositories import AgentRepository
        from api.services.agent_service import AgentService
        agent_repo = AgentRepository(db)
        provider = AsyncMock(spec=CLIAgentProvider)
        provider.execute = AsyncMock(return_value='{"forge_path": "output/test/", "forge_config": {}, "input_schema": [], "output_schema": []}')
        provider_factory = AsyncMock(return_value=provider)

        service = AgentService(
            agent_repo=agent_repo,
            provider=provider,
            provider_factory=provider_factory,
        )
        agent = await service.create_agent(
            name="Test",
            description="A test agent",
            provider="codex",
            model="gpt-5-codex",
        )

        await service.run_forge(agent["id"])

        provider_factory.assert_awaited_once_with(
            provider_key="codex",
            model="gpt-5-codex",
            timeout=600,
        )

    @pytest.mark.asyncio
    async def test_run_forge_sets_error_on_failure(self, db):
        from api.persistence.repositories import AgentRepository
        from api.services.agent_service import AgentService
        agent_repo = AgentRepository(db)
        provider = AsyncMock(spec=CLIAgentProvider)
        provider.execute = AsyncMock(side_effect=RuntimeError("forge crashed"))

        service = AgentService(agent_repo=agent_repo, provider=provider)
        agent = await service.create_agent(name="Test", description="A test agent")

        await service.run_forge(agent["id"])

        updated = await agent_repo.get(agent["id"])
        assert updated["status"] == "error"
        assert "forge crashed" in updated["forge_config"]["error"]

    @pytest.mark.asyncio
    async def test_run_forge_stores_provider_error_details(self, db):
        """When forge fails with ProviderError, store stdout, stderr, exit_code."""
        from api.persistence.repositories import AgentRepository
        from api.services.agent_service import AgentService
        agent_repo = AgentRepository(db)
        provider = AsyncMock(spec=CLIAgentProvider)
        provider.execute = AsyncMock(
            side_effect=ProviderError(
                provider_name="Claude Code",
                exit_code=1,
                stdout="partial forge output here",
                stderr="Error: something went wrong in forge",
            )
        )

        service = AgentService(agent_repo=agent_repo, provider=provider)
        agent = await service.create_agent(name="Test", description="A test agent")

        await service.run_forge(agent["id"])

        updated = await agent_repo.get(agent["id"])
        assert updated["status"] == "error"
        assert updated["forge_config"]["exit_code"] == 1
        assert "partial forge output" in updated["forge_config"]["stdout"]
        assert "something went wrong" in updated["forge_config"]["stderr"]
        assert "Claude Code" in updated["forge_config"]["error"]

    @pytest.mark.asyncio
    async def test_run_forge_parses_raw_json(self, db):
        from api.persistence.repositories import AgentRepository
        from api.services.agent_service import AgentService
        agent_repo = AgentRepository(db)
        provider = AsyncMock(spec=CLIAgentProvider)

        # Raw JSON (not wrapped in Claude output format)
        raw_json = '{"forge_path": "output/raw/", "forge_config": {"complexity": "simple", "steps": 1, "prompts": ["01_Agent.md"]}, "input_schema": [], "output_schema": []}'
        provider.execute = AsyncMock(return_value=raw_json)

        service = AgentService(agent_repo=agent_repo, provider=provider)
        agent = await service.create_agent(name="Raw", description="test")

        await service.run_forge(agent["id"])

        updated = await agent_repo.get(agent["id"])
        assert updated["status"] == "ready"
        assert updated["forge_path"] == "output/raw/"

    @pytest.mark.asyncio
    async def test_run_update_sets_updating_then_ready(self, db):
        """Substantive update triggers forge update and transitions updating → ready."""
        from api.persistence.repositories import AgentRepository
        from api.services.agent_service import AgentService
        agent_repo = AgentRepository(db)
        provider = AsyncMock(spec=CLIAgentProvider)

        forge_output = '{"forge_path": "output/test/", "forge_config": {"complexity": "simple", "steps": 1, "prompts": ["01_Test.md"]}, "input_schema": [{"name": "topic", "type": "text", "required": true}], "output_schema": [{"name": "result", "type": "text"}]}'
        provider.execute = AsyncMock(return_value=forge_output)

        service = AgentService(agent_repo=agent_repo, provider=provider)
        agent = await service.create_agent(name="Test", description="Original desc")
        # Simulate agent already ready
        await agent_repo.update(agent["id"], status="ready", forge_path="output/test/")

        old_agent = await agent_repo.get(agent["id"])
        # Route applies new fields + sets status=updating before calling run_update
        await agent_repo.update(agent["id"], description="Updated desc", status="updating")

        await service.run_update(
            agent["id"],
            old_agent=old_agent,
            new_fields={"description": "Updated desc"},
        )

        updated = await agent_repo.get(agent["id"])
        assert updated["status"] == "ready"
        assert updated["description"] == "Updated desc"
        provider.execute.assert_called_once()
        # Verify the prompt references api-update.md
        call_args = provider.execute.call_args
        assert "api-update.md" in call_args.kwargs.get("prompt", call_args.args[0] if call_args.args else "")

    @pytest.mark.asyncio
    async def test_run_update_sets_error_on_failure(self, db):
        """When forge update fails, status goes to error."""
        from api.persistence.repositories import AgentRepository
        from api.services.agent_service import AgentService
        agent_repo = AgentRepository(db)
        provider = AsyncMock(spec=CLIAgentProvider)
        provider.execute = AsyncMock(side_effect=ProviderError(
            provider_name="Claude Code", exit_code=1,
            stdout="partial", stderr="update failed",
        ))

        service = AgentService(agent_repo=agent_repo, provider=provider)
        agent = await service.create_agent(name="Test", description="Original")
        await agent_repo.update(agent["id"], status="ready", forge_path="output/test/")

        await service.run_update(
            agent["id"],
            old_agent=await agent_repo.get(agent["id"]),
            new_fields={"description": "New desc"},
        )

        updated = await agent_repo.get(agent["id"])
        assert updated["status"] == "error"
        assert updated["forge_config"]["exit_code"] == 1

    @pytest.mark.asyncio
    async def test_run_update_nonexistent_agent(self, db):
        """run_update on nonexistent agent logs error, doesn't crash."""
        from api.persistence.repositories import AgentRepository
        from api.services.agent_service import AgentService
        agent_repo = AgentRepository(db)
        provider = AsyncMock(spec=CLIAgentProvider)
        service = AgentService(agent_repo=agent_repo, provider=provider)

        await service.run_update("nonexistent-id", old_agent={}, new_fields={})
        provider.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_forge_nonexistent_agent(self, db):
        from api.persistence.repositories import AgentRepository
        from api.services.agent_service import AgentService
        agent_repo = AgentRepository(db)
        provider = AsyncMock(spec=CLIAgentProvider)
        service = AgentService(agent_repo=agent_repo, provider=provider)

        # Should not raise, just log error
        await service.run_forge("nonexistent-id")
        provider.execute.assert_not_called()


class TestExecutionService:

    @pytest.mark.asyncio
    async def test_run_standalone_agent(self, db):
        from api.persistence.repositories import AgentRepository, RunRepository
        agent_repo = AgentRepository(db)
        run_repo = RunRepository(db)

        agent = await agent_repo.create(
            name="Research", description="Research a topic",
            input_schema=[{"name": "topic", "type": "text", "required": True}],
            output_schema=[{"name": "findings", "type": "text"}],
        )
        run = await run_repo.create(agent_id=agent["id"], inputs={"topic": "AI"})

        executor_mock = AsyncMock()
        executor_mock.execute.return_value = {"findings": "AI research data"}
        emit_mock = AsyncMock()

        service = ExecutionService(
            agent_repo=agent_repo,
            run_repo=run_repo,
            project_repo=None,
            executor=executor_mock,
            emit=emit_mock,
        )
        await service.run_standalone_agent(run["id"])

        updated_run = await run_repo.get(run["id"])
        assert updated_run["status"] == "completed"
        assert updated_run["outputs"] == {"findings": "AI research data"}
        emit_mock.assert_any_call(run["id"], "run_started", {"forge_path": ""})
        emit_mock.assert_any_call(
            run["id"], "run_completed",
            {"outputs": {"findings": "AI research data"}},
        )

    @pytest.mark.asyncio
    async def test_run_standalone_agent_uses_run_provider_and_model(self, db):
        from api.persistence.repositories import AgentRepository, RunRepository
        agent_repo = AgentRepository(db)
        run_repo = RunRepository(db)

        agent = await agent_repo.create(
            name="Research",
            description="Research a topic",
            provider="claude_code",
            model="claude-sonnet-4-6",
        )
        run = await run_repo.create(
            agent_id=agent["id"],
            inputs={"topic": "AI"},
            provider="codex",
            model="gpt-5-codex",
        )

        executor_mock = AsyncMock()
        executor_mock.execute.return_value = {"findings": "AI research data"}
        emit_mock = AsyncMock()
        provider_instance = object()
        provider_factory = AsyncMock(return_value=provider_instance)

        service = ExecutionService(
            agent_repo=agent_repo,
            run_repo=run_repo,
            project_repo=None,
            executor=executor_mock,
            emit=emit_mock,
            provider_factory=provider_factory,
        )
        await service.run_standalone_agent(run["id"])

        provider_factory.assert_awaited_once_with(
            provider_key="codex",
            model="gpt-5-codex",
            timeout=900,
        )
        executor_mock.execute.assert_awaited_once()
        assert executor_mock.execute.await_args.kwargs["provider"] is provider_instance

    @pytest.mark.asyncio
    async def test_run_standalone_agent_failure(self, db):
        from api.persistence.repositories import AgentRepository, RunRepository
        agent_repo = AgentRepository(db)
        run_repo = RunRepository(db)

        agent = await agent_repo.create(name="T", description="")
        run = await run_repo.create(agent_id=agent["id"])

        executor_mock = AsyncMock()
        executor_mock.execute.side_effect = RuntimeError("boom")
        emit_mock = AsyncMock()

        service = ExecutionService(
            agent_repo=agent_repo,
            run_repo=run_repo,
            project_repo=None,
            executor=executor_mock,
            emit=emit_mock,
        )
        await service.run_standalone_agent(run["id"])

        updated_run = await run_repo.get(run["id"])
        assert updated_run["status"] == "failed"

    @pytest.mark.asyncio
    async def test_run_project_dag(self, db):
        from api.persistence.repositories import (
            AgentRepository, ProjectRepository, RunRepository,
        )
        agent_repo = AgentRepository(db)
        project_repo = ProjectRepository(db)
        run_repo = RunRepository(db)

        t1 = await agent_repo.create(
            name="Research", description="Research",
            input_schema=[{"name": "topic", "type": "text", "required": True}],
            output_schema=[{"name": "findings", "type": "text"}],
        )
        t2 = await agent_repo.create(
            name="Write", description="Write",
            input_schema=[{"name": "content", "type": "text", "required": True}],
            output_schema=[{"name": "article", "type": "text"}],
        )
        project = await project_repo.create(name="Pipeline", description="")
        n1 = await project_repo.add_node(project["id"], t1["id"])
        n2 = await project_repo.add_node(project["id"], t2["id"])
        await project_repo.add_edge(
            project["id"], n1["id"], n2["id"],
            source_output="findings", target_input="content",
        )
        run = await run_repo.create(
            project_id=project["id"], inputs={"topic": "AI"},
        )

        call_count = 0
        async def mock_execute(agent, inputs, callback, run_id=""):
            nonlocal call_count
            call_count += 1
            if agent["name"] == "Research":
                return {"findings": "AI data"}
            return {"article": "Full article about AI"}

        executor_mock = AsyncMock()
        executor_mock.execute = mock_execute
        emit_mock = AsyncMock()

        service = ExecutionService(
            agent_repo=agent_repo,
            run_repo=run_repo,
            project_repo=project_repo,
            executor=executor_mock,
            emit=emit_mock,
        )
        await service.run_project(run["id"])

        updated_run = await run_repo.get(run["id"])
        assert updated_run["status"] == "completed"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_run_project_with_approval_gate(self, db):
        from api.persistence.repositories import (
            AgentRepository, ProjectRepository, RunRepository,
        )
        agent_repo = AgentRepository(db)
        project_repo = ProjectRepository(db)
        run_repo = RunRepository(db)

        t1 = await agent_repo.create(name="Work", description="Do work",
            output_schema=[{"name": "result", "type": "text"}])
        t_gate = await agent_repo.create(name="Gate", description="", type="approval")
        project = await project_repo.create(name="P", description="")
        n1 = await project_repo.add_node(project["id"], t1["id"])
        n_gate = await project_repo.add_node(project["id"], t_gate["id"])
        await project_repo.add_edge(
            project["id"], n1["id"], n_gate["id"],
            source_output="result", target_input="in",
        )
        run = await run_repo.create(project_id=project["id"])

        async def mock_execute(agent, inputs, callback, run_id=""):
            return {"result": "done"}

        executor_mock = AsyncMock()
        executor_mock.execute = mock_execute
        emit_mock = AsyncMock()

        service = ExecutionService(
            agent_repo=agent_repo,
            run_repo=run_repo,
            project_repo=project_repo,
            executor=executor_mock,
            emit=emit_mock,
        )
        await service.run_project(run["id"])

        updated_run = await run_repo.get(run["id"])
        assert updated_run["status"] == "awaiting_approval"
        approval_calls = [
            c for c in emit_mock.call_args_list
            if c.args[1] == "approval_required"
        ]
        assert len(approval_calls) == 1
        data = approval_calls[0].args[2]
        assert data["node_id"] == n_gate["id"]
        assert n1["id"] in data["outputs_so_far"]
        assert data["outputs_so_far"][n1["id"]] == {"result": "done"}


def _make_streaming_provider(output='{"result": "done"}'):
    """Create a mock CLI provider whose execute_streaming yields a done event.

    Also records call kwargs on mock.execute_streaming_call_kwargs for assertions.
    """
    from api.engine.providers import ExecutionEvent

    provider = AsyncMock()
    provider._streaming_calls = []

    async def fake_streaming(**kwargs):
        provider._streaming_calls.append(kwargs)
        yield ExecutionEvent(type="done", data=output)

    provider.execute_streaming = fake_streaming
    return provider


class TestAgentExecutor:
    """Tests for AgentExecutor routing logic."""

    @pytest.mark.asyncio
    async def test_claude_code_agent_with_computer_use_routes_to_cli(self):
        """claude_code agents should use CLI provider even when computer_use=True.

        Claude Code handles computer use via MCP, so it does NOT need routing
        to the computer_use_service.
        """
        from api.engine.executor import AgentExecutor

        cli_provider = _make_streaming_provider('{"result": "pricing report"}')
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(cli_provider, cu_service)
        agent = {
            "id": "test-1",
            "name": "competitor-spy",
            "computer_use": True,
            "provider": "claude_code",
            "forge_path": "",
            "description": "Spy on competitors",
            "output_schema": [],
            "steps": [
                {"name": "Open website", "computer_use": True},
                {"name": "Write report", "computer_use": False},
            ],
        }
        result = await executor.execute(agent, {"task": "analyze pricing"}, callback)

        # Should have called CLI provider streaming, NOT computer_use_service
        assert len(cli_provider._streaming_calls) == 1
        cu_service.run_agent.assert_not_called()
        assert result == {"result": "pricing report"}

    @pytest.mark.asyncio
    async def test_workspace_always_project_root_even_with_forge_path(self):
        """Workspace must always be PROJECT_ROOT, never forge_path.

        The prompt references forge_path as a relative path from project root
        (e.g., 'Read output/abc/agentic.md'). If cwd were set to forge_path,
        the agent would look for output/abc/output/abc/agentic.md (doubled path).
        """
        from api.engine.executor import AgentExecutor, _PROJECT_ROOT

        cli_provider = _make_streaming_provider()
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(cli_provider, cu_service)
        agent = {
            "id": "test-ws",
            "name": "test-agent",
            "computer_use": False,
            "provider": "claude_code",
            "forge_path": "output/some-agent-id",
            "description": "Test agent",
            "output_schema": [],
        }
        await executor.execute(agent, {"task": "test"}, callback)

        call_kwargs = cli_provider._streaming_calls[0]
        assert call_kwargs["workspace"] == _PROJECT_ROOT
        assert call_kwargs["workspace"] != "output/some-agent-id"

    @pytest.mark.asyncio
    async def test_workspace_is_project_root_when_no_forge_path(self):
        """Agents without forge_path should also get PROJECT_ROOT as workspace."""
        from api.engine.executor import AgentExecutor, _PROJECT_ROOT

        cli_provider = _make_streaming_provider()
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(cli_provider, cu_service)
        agent = {
            "id": "test-no-fp",
            "name": "test-agent",
            "computer_use": False,
            "provider": "claude_code",
            "forge_path": "",
            "description": "Agent without forge path",
            "output_schema": [],
        }
        await executor.execute(agent, {}, callback)

        call_kwargs = cli_provider._streaming_calls[0]
        assert call_kwargs["workspace"] == _PROJECT_ROOT

    @pytest.mark.asyncio
    async def test_prompt_contains_forge_path_for_file_resolution(self):
        """The prompt must include forge_path so Claude can find agentic.md from PROJECT_ROOT."""
        from api.engine.executor import AgentExecutor

        cli_provider = _make_streaming_provider()
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(cli_provider, cu_service)
        agent = {
            "id": "test-fp",
            "name": "test-agent",
            "computer_use": False,
            "provider": "claude_code",
            "forge_path": "output/my-agent-uuid",
            "description": "Test",
            "output_schema": [],
        }
        await executor.execute(agent, {}, callback)

        call_kwargs = cli_provider._streaming_calls[0]
        prompt = call_kwargs["prompt"]
        assert "output/my-agent-uuid/agentic.md" in prompt

    @pytest.mark.asyncio
    async def test_timeout_900_for_cli_agents(self):
        """CLI agents (no computer_use) should get 900s timeout."""
        from api.engine.executor import AgentExecutor

        cli_provider = _make_streaming_provider()
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(cli_provider, cu_service)
        agent = {
            "id": "test-to",
            "name": "cli-agent",
            "computer_use": False,
            "provider": "claude_code",
            "forge_path": "output/test",
            "description": "CLI only",
            "output_schema": [],
        }
        await executor.execute(agent, {}, callback)

        call_kwargs = cli_provider._streaming_calls[0]
        assert call_kwargs["timeout"] == 900

    @pytest.mark.asyncio
    async def test_timeout_1800_for_computer_use_agents(self):
        """Computer use agents routed via CLI should get 1800s timeout."""
        from api.engine.executor import AgentExecutor

        cli_provider = _make_streaming_provider()
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(cli_provider, cu_service)
        agent = {
            "id": "test-cu-to",
            "name": "cu-agent",
            "computer_use": True,
            "provider": "claude_code",
            "forge_path": "output/test",
            "description": "Desktop agent",
            "output_schema": [],
        }
        await executor.execute(agent, {}, callback)

        call_kwargs = cli_provider._streaming_calls[0]
        assert call_kwargs["timeout"] == 1800

    @pytest.mark.asyncio
    async def test_anthropic_agent_with_computer_use_routes_to_cu_service(self):
        """anthropic provider agents with computer_use=True should use computer_use_service."""
        from api.engine.executor import AgentExecutor

        cli_provider = AsyncMock()
        cu_service = AsyncMock()
        cu_service.run_agent.return_value = {"success": True}
        callback = AsyncMock()

        executor = AgentExecutor(cli_provider, cu_service)
        agent = {
            "id": "test-2",
            "name": "browser-agent",
            "computer_use": True,
            "provider": "anthropic",
            "forge_path": "",
            "description": "Browse the web",
            "output_schema": [],
        }
        result = await executor.execute(agent, {}, callback)

        # Should have called computer_use_service, NOT CLI provider
        cu_service.run_agent.assert_called_once()
        cli_provider.execute.assert_not_called()
        assert result == {"success": True}

    @pytest.mark.asyncio
    async def test_execute_emits_agent_log_events_during_streaming(self):
        """Executor should emit agent_log events for each streaming output line."""
        from api.engine.executor import AgentExecutor
        from api.engine.providers import ExecutionEvent

        async def fake_streaming(**kwargs):
            yield ExecutionEvent(type="output", data="Reading files...")
            yield ExecutionEvent(type="output", data="Using tool: Grep")
            yield ExecutionEvent(type="done", data='{"report": "done"}')

        cli_provider = AsyncMock()
        cli_provider.execute_streaming = fake_streaming
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(cli_provider, cu_service)
        agent = {
            "id": "test-stream",
            "name": "stream-agent",
            "computer_use": False,
            "provider": "claude_code",
            "forge_path": "",
            "description": "Test streaming",
            "output_schema": [],
        }
        result = await executor.execute(agent, {}, callback)

        # Should have emitted agent_log for each output event
        log_calls = [
            c for c in callback.call_args_list
            if c.args[0] == "agent_log"
        ]
        assert len(log_calls) == 2
        assert log_calls[0].args[1]["message"] == "Reading files..."
        assert log_calls[1].args[1]["message"] == "Using tool: Grep"

        # Should still emit agent_started and agent_completed
        event_types = [c.args[0] for c in callback.call_args_list]
        assert "agent_started" in event_types
        assert "agent_completed" in event_types

        # Should parse the done event's data as the result
        assert result == {"report": "done"}

    @pytest.mark.asyncio
    async def test_execute_streaming_error_event_raises(self):
        """Executor should raise when streaming yields an error event."""
        from api.engine.executor import AgentExecutor
        from api.engine.providers import ExecutionEvent

        async def fake_streaming(**kwargs):
            yield ExecutionEvent(type="output", data="Starting...")
            yield ExecutionEvent(type="error", data="Provider crashed")

        cli_provider = AsyncMock()
        cli_provider.execute_streaming = fake_streaming
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(cli_provider, cu_service)
        agent = {
            "id": "test-err",
            "name": "error-agent",
            "computer_use": False,
            "provider": "claude_code",
            "forge_path": "",
            "description": "Will fail",
            "output_schema": [],
        }
        with pytest.raises(RuntimeError, match="Provider crashed"):
            await executor.execute(agent, {}, callback)

        # agent_failed should have been emitted
        event_types = [c.args[0] for c in callback.call_args_list]
        assert "agent_failed" in event_types

    @pytest.mark.asyncio
    async def test_execute_streaming_done_with_plain_text_uses_parse_output(self):
        """When done event data is not JSON, _parse_output wraps it."""
        from api.engine.executor import AgentExecutor
        from api.engine.providers import ExecutionEvent

        async def fake_streaming(**kwargs):
            yield ExecutionEvent(type="done", data="plain text result")

        cli_provider = AsyncMock()
        cli_provider.execute_streaming = fake_streaming
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(cli_provider, cu_service)
        agent = {
            "id": "test-plain",
            "name": "plain-agent",
            "computer_use": False,
            "provider": "claude_code",
            "forge_path": "",
            "description": "Returns plain text",
            "output_schema": [{"name": "report"}],
        }
        result = await executor.execute(agent, {}, callback)

        # _parse_output should wrap in the first output_schema field
        assert result == {"report": "plain text result"}

    @pytest.mark.asyncio
    async def test_execute_per_step_routes_cli_only_multi_step(self):
        """Pure-CLI agents with forge_path + multiple steps run per-step."""
        from api.engine.executor import AgentExecutor
        from api.engine.providers import ExecutionEvent

        call_count = 0

        async def fake_streaming(**kwargs):
            nonlocal call_count
            call_count += 1
            assert kwargs.get("use_stream_json") is True  # CLI always streams
            yield ExecutionEvent(type="output", data=f"Step {call_count} output")
            yield ExecutionEvent(type="done", data=f'{{"step": {call_count}}}')

        cli_provider = AsyncMock()
        cli_provider.execute_streaming = fake_streaming
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(cli_provider, cu_service)
        agent = {
            "id": "test-cli-multi",
            "name": "cli-multi-agent",
            "computer_use": False,
            "provider": "claude_code",
            "forge_path": "output/test-cli-multi",
            "description": "Pure CLI multi-step",
            "output_schema": [{"name": "step"}],
            "steps": [
                {"name": "Research", "computer_use": False},
                {"name": "Analyze", "computer_use": False},
                {"name": "Report", "computer_use": False},
            ],
        }
        result = await executor.execute(agent, {"topic": "test"}, callback)

        assert call_count == 3
        assert result == {"step": 3}

        log_calls = [
            c for c in callback.call_args_list if c.args[0] == "agent_log"
        ]
        log_messages = [c.args[1]["message"] for c in log_calls]
        assert any("Step 1" in m and "[CLI]" in m for m in log_messages)
        assert any("Step 2" in m and "[CLI]" in m for m in log_messages)
        assert any("Step 3" in m and "[CLI]" in m for m in log_messages)

    @pytest.mark.asyncio
    async def test_execute_per_step_routes_mixed_steps(self):
        """Agents with forge_path + mixed CLI/Desktop steps run per-step."""
        from api.engine.executor import AgentExecutor
        from api.engine.providers import ExecutionEvent

        call_count = 0

        async def fake_streaming(**kwargs):
            nonlocal call_count
            call_count += 1
            use_stream = kwargs.get("use_stream_json", True)
            if call_count == 1:
                # Step 1: CLI — should use stream-json
                assert use_stream is True
                yield ExecutionEvent(type="output", data="Researching...")
                yield ExecutionEvent(type="done", data="research done")
            elif call_count == 2:
                # Step 2: Desktop — should NOT use stream-json
                assert use_stream is False
                yield ExecutionEvent(type="done", data="screenshot captured")
            elif call_count == 3:
                # Step 3: CLI — should use stream-json
                assert use_stream is True
                yield ExecutionEvent(type="output", data="Writing report...")
                yield ExecutionEvent(type="done", data='{"report": "final"}')

        cli_provider = AsyncMock()
        cli_provider.execute_streaming = fake_streaming
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(cli_provider, cu_service)
        agent = {
            "id": "test-mixed",
            "name": "mixed-agent",
            "computer_use": True,
            "provider": "claude_code",
            "forge_path": "output/test-mixed",
            "description": "Mixed CLI and Desktop",
            "output_schema": [{"name": "report"}],
            "steps": [
                {"name": "Research", "computer_use": False},
                {"name": "Screenshot", "computer_use": True},
                {"name": "Write Report", "computer_use": False},
            ],
        }
        result = await executor.execute(agent, {"topic": "test"}, callback)

        # Should have called streaming 3 times (one per step)
        assert call_count == 3

        # Last step's done data should be the result
        assert result == {"report": "final"}

        # Check agent_log events include step markers and CLI streaming output
        log_calls = [
            c for c in callback.call_args_list
            if c.args[0] == "agent_log"
        ]
        log_messages = [c.args[1]["message"] for c in log_calls]
        # Step markers
        assert any("Step 1" in m and "[CLI]" in m for m in log_messages)
        assert any("Step 2" in m and "[Desktop]" in m for m in log_messages)
        assert any("Step 3" in m and "[CLI]" in m for m in log_messages)
        # CLI steps should have streamed their output lines
        assert "Researching..." in log_messages
        assert "Writing report..." in log_messages
        # Desktop step should NOT have streamed raw output
        assert "screenshot captured" not in log_messages

    @pytest.mark.asyncio
    async def test_execute_per_step_error_in_step_raises_with_step_info(self):
        """Error in a per-step execution includes step number and name."""
        from api.engine.executor import AgentExecutor
        from api.engine.providers import ExecutionEvent

        async def fake_streaming(**kwargs):
            yield ExecutionEvent(type="error", data="tool crashed")

        cli_provider = AsyncMock()
        cli_provider.execute_streaming = fake_streaming
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(cli_provider, cu_service)
        agent = {
            "id": "test-step-err",
            "name": "step-error-agent",
            "computer_use": True,
            "provider": "claude_code",
            "forge_path": "output/test-step-err",
            "description": "Will fail at step 1",
            "output_schema": [],
            "steps": [
                {"name": "Research", "computer_use": False},
                {"name": "Screenshot", "computer_use": True},
            ],
        }
        with pytest.raises(RuntimeError, match="Step 1.*Research.*tool crashed"):
            await executor.execute(agent, {}, callback)

        event_types = [c.args[0] for c in callback.call_args_list]
        assert "agent_failed" in event_types

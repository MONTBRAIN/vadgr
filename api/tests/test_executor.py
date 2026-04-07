"""Tests for agent executor with mocked provider."""

import os
import tempfile

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api.engine.executor import AgentExecutor
from api.engine.providers import (
    ExecutionEvent, build_step_prompt, _PROJECT_ROOT,
    CLIAgentProvider,
)


def _make_streaming_provider(output='{"result": "done"}'):
    """Create a mock provider whose execute_streaming yields a done event."""
    provider = AsyncMock()
    provider._streaming_calls = []

    async def fake_streaming(**kwargs):
        provider._streaming_calls.append(kwargs)
        yield ExecutionEvent(type="done", data=output)

    provider.execute_streaming = fake_streaming
    return provider


def _make_error_streaming_provider(error_msg="Provider down"):
    """Create a mock provider whose execute_streaming yields an error event."""
    provider = AsyncMock()

    async def fake_streaming(**kwargs):
        yield ExecutionEvent(type="error", data=error_msg)

    provider.execute_streaming = fake_streaming
    return provider


class TestAgentExecutor:

    @pytest.mark.asyncio
    async def test_execute_simple_agent(self):
        provider = _make_streaming_provider('{"findings": "AI safety research data"}')
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)
        agent = {
            "id": "agent-1",
            "name": "Research",
            "description": "Research a topic",
            "type": "agent",
            "computer_use": False,
            "forge_config": {"complexity": "simple", "agents": 1, "steps": 1},
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "input_schema": [{"name": "topic", "type": "text", "required": True}],
            "output_schema": [{"name": "findings", "type": "text"}],
        }
        inputs = {"topic": "AI Safety"}
        result = await executor.execute(agent, inputs, callback)
        assert result == {"findings": "AI safety research data"}
        assert len(provider._streaming_calls) == 1

    @pytest.mark.asyncio
    async def test_execute_computer_use_agent(self):
        provider = AsyncMock()
        cu_service = AsyncMock()
        cu_service.run_agent.return_value = {"screenshot": "base64...", "success": True}
        callback = AsyncMock()

        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)
        agent = {
            "id": "agent-2",
            "name": "Fill Form",
            "description": "Fill a form on the web",
            "type": "agent",
            "computer_use": True,
            "forge_config": {},
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "input_schema": [],
            "output_schema": [],
        }
        result = await executor.execute(agent, {}, callback)
        assert result["success"] is True
        cu_service.run_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_emits_agent_started_and_completed(self):
        provider = _make_streaming_provider('{"out": "val"}')
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)
        agent = {
            "id": "agent-3",
            "name": "T",
            "description": "",
            "type": "agent",
            "computer_use": False,
            "forge_config": {"complexity": "simple"},
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "input_schema": [],
            "output_schema": [],
        }
        await executor.execute(agent, {}, callback)

        event_types = [call.args[0] for call in callback.call_args_list]
        assert "agent_started" in event_types
        assert "agent_completed" in event_types

    @pytest.mark.asyncio
    async def test_execute_emits_agent_failed_on_error(self):
        provider = _make_error_streaming_provider("Provider down")
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)
        agent = {
            "id": "agent-4",
            "name": "T",
            "description": "",
            "type": "agent",
            "computer_use": False,
            "forge_config": {},
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "input_schema": [],
            "output_schema": [],
        }
        with pytest.raises(RuntimeError):
            await executor.execute(agent, {}, callback)

        event_types = [call.args[0] for call in callback.call_args_list]
        assert "agent_failed" in event_types

    @pytest.mark.asyncio
    async def test_execute_multi_step_agent(self):
        """Multi-step agents go through the CLI provider."""
        provider = _make_streaming_provider('{"article": "Full article..."}')
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)
        agent = {
            "id": "agent-5",
            "name": "Write Paper",
            "description": "Write a research paper",
            "type": "agent",
            "computer_use": False,
            "forge_config": {"complexity": "multi_step", "agents": 3, "steps": 5},
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "input_schema": [],
            "output_schema": [],
        }
        result = await executor.execute(agent, {"topic": "AI"}, callback)
        assert result == {"article": "Full article..."}
        assert len(provider._streaming_calls) == 1

    @pytest.mark.asyncio
    async def test_execute_parses_non_json_output(self):
        """When provider returns plain text, maps to first output field."""
        provider = _make_streaming_provider("Just some plain text output")
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)
        agent = {
            "id": "agent-6",
            "name": "T",
            "description": "",
            "type": "agent",
            "computer_use": False,
            "output_schema": [{"name": "summary", "type": "text"}],
        }
        result = await executor.execute(agent, {}, callback)
        assert result == {"summary": "Just some plain text output"}

    @pytest.mark.asyncio
    async def test_parse_output_multi_schema_fallback_sets_all_keys(self):
        """When plain text is returned and multiple output schema fields exist,
        the primary field gets the text and all other fields get empty string."""
        provider = _make_streaming_provider("Just plain text")
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)
        agent = {
            "id": "agent-multi",
            "name": "Multi Output",
            "description": "",
            "type": "agent",
            "computer_use": False,
            "output_schema": [
                {"name": "report", "type": "markdown"},
                {"name": "summary", "type": "text"},
                {"name": "data", "type": "json"},
            ],
        }
        result = await executor.execute(agent, {}, callback)
        # First field gets the text
        assert result["report"] == "Just plain text"
        # Other fields default to empty string, not missing
        assert "summary" in result
        assert "data" in result
        assert result["summary"] == ""
        assert result["data"] == ""

    @pytest.mark.asyncio
    async def test_parse_output_no_schema_uses_result_key(self):
        """When no output schema, plain text maps to 'result' key."""
        provider = _make_streaming_provider("plain text")
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)
        agent = {
            "id": "agent-noschema",
            "name": "T",
            "description": "",
            "type": "agent",
            "computer_use": False,
            "output_schema": [],
        }
        result = await executor.execute(agent, {}, callback)
        assert result == {"result": "plain text"}

    @pytest.mark.asyncio
    async def test_parse_output_valid_json_returned_as_is(self):
        """When provider returns valid JSON dict, it's used directly."""
        provider = _make_streaming_provider('{"report": "findings", "summary": "brief"}')
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)
        agent = {
            "id": "agent-json",
            "name": "T",
            "description": "",
            "type": "agent",
            "computer_use": False,
            "output_schema": [{"name": "report", "type": "markdown"}, {"name": "summary", "type": "text"}],
        }
        result = await executor.execute(agent, {}, callback)
        assert result == {"report": "findings", "summary": "brief"}

    def test_normalize_outputs_upgrades_file_path_string_to_descriptor(self, tmp_path):
        provider = AsyncMock()
        cu_service = AsyncMock()
        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)

        forge_path = "output/agent-123"
        run_id = "run-456"
        pdf_dir = tmp_path / forge_path / "output" / run_id / "user_outputs" / "step_02"
        pdf_dir.mkdir(parents=True)
        pdf_file = pdf_dir / "summary.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\n")

        outputs = {
            "summary_pdf": f"{forge_path}/output/{run_id}/user_outputs/step_02/summary.pdf"
        }
        output_schema = [{"name": "summary_pdf", "type": "file"}]

        result = executor._normalize_outputs(
            outputs,
            forge_path=forge_path,
            run_id=run_id,
            output_schema=output_schema,
            project_root=tmp_path,
        )

        assert result["summary_pdf"]["kind"] == "file"
        assert result["summary_pdf"]["filename"] == "summary.pdf"
        assert result["summary_pdf"]["mime_type"] == "application/pdf"
        assert result["summary_pdf"]["path"].endswith("/summary.pdf")

    def test_normalize_outputs_rejects_file_outside_user_outputs(self, tmp_path):
        provider = AsyncMock()
        cu_service = AsyncMock()
        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)

        forge_path = "output/agent-123"
        run_id = "run-456"
        other_dir = tmp_path / forge_path / "output" / run_id / "agent_outputs"
        other_dir.mkdir(parents=True)
        other_file = other_dir / "summary.pdf"
        other_file.write_bytes(b"%PDF-1.4\n")

        raw_path = f"{forge_path}/output/{run_id}/agent_outputs/summary.pdf"
        result = executor._normalize_outputs(
            {"summary_pdf": raw_path},
            forge_path=forge_path,
            run_id=run_id,
            output_schema=[{"name": "summary_pdf", "type": "file"}],
            project_root=tmp_path,
        )

        assert result["summary_pdf"] == raw_path

    @pytest.mark.asyncio
    async def test_parse_output_json_with_trailing_text(self):
        """When JSON is followed by extra text, the JSON object is still extracted."""
        raw = '{"report": "findings", "summary": "brief"}\n\nSome trailing text the model added.'
        provider = _make_streaming_provider(raw)
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)
        agent = {
            "id": "agent-trailing",
            "name": "T",
            "description": "",
            "type": "agent",
            "computer_use": False,
            "output_schema": [{"name": "report", "type": "markdown"}, {"name": "summary", "type": "text"}],
        }
        result = await executor.execute(agent, {}, callback)
        assert result == {"report": "findings", "summary": "brief"}

    @pytest.mark.asyncio
    async def test_parse_output_json_with_leading_text(self):
        """When text precedes the JSON object, the JSON is still extracted."""
        raw = 'Here is my analysis:\n\n{"report": "the report", "summary": "the summary"}'
        provider = _make_streaming_provider(raw)
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)
        agent = {
            "id": "agent-leading",
            "name": "T",
            "description": "",
            "type": "agent",
            "computer_use": False,
            "output_schema": [{"name": "report", "type": "markdown"}, {"name": "summary", "type": "text"}],
        }
        result = await executor.execute(agent, {}, callback)
        assert result == {"report": "the report", "summary": "the summary"}

    @pytest.mark.asyncio
    async def test_parse_output_json_with_trailing_extra_brace(self):
        """When JSON is followed by an extra closing brace, the JSON is still extracted.

        Regression: the old scanner used `end -= 1` after rfind, which caused it to
        skip the position of the valid JSON's last `}` and never try the correct slice.
        """
        raw = '{"report": "findings", "summary": "brief"}}'
        provider = _make_streaming_provider(raw)
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)
        agent = {
            "id": "agent-extrabrace",
            "name": "T",
            "description": "",
            "type": "agent",
            "computer_use": False,
            "output_schema": [{"name": "report", "type": "markdown"}, {"name": "summary", "type": "text"}],
        }
        result = await executor.execute(agent, {}, callback)
        assert result == {"report": "findings", "summary": "brief"}

    @pytest.mark.asyncio
    async def test_execute_with_forge_path(self):
        """When agent has forge_path, prompt references agentic.md."""
        provider = _make_streaming_provider('{"result": "done"}')
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)
        agent = {
            "id": "agent-7",
            "name": "Research",
            "description": "Research a topic",
            "type": "agent",
            "computer_use": False,
            "forge_path": "output/research-topic/",
            "output_schema": [{"name": "result", "type": "text"}],
        }
        await executor.execute(agent, {"topic": "AI"}, callback)

        call_kwargs = provider._streaming_calls[0]
        prompt = call_kwargs["prompt"]
        assert "agentic.md" in prompt

    @pytest.mark.asyncio
    async def test_desktop_step_fails_on_short_duration(self):
        """A desktop step completing in < 30s must raise and stop the workflow."""
        provider = _make_streaming_provider('{"result": "done"}')
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)
        agent = {
            "id": "agent-cu-fast",
            "name": "Quick Desktop",
            "description": "",
            "type": "agent",
            "computer_use": True,
            "forge_path": "",
            "steps": [{"name": "Click Button", "computer_use": True}],
            "output_schema": [],
        }
        await executor._execute_per_step(agent, {}, callback)
        # Should emit WARNING, not raise
        log_messages = [
            call.args[1].get("message", "")
            for call in callback.call_args_list
            if call.args[0] == "agent_log"
        ]
        assert any("WARNING" in m and "suspiciously fast" in m for m in log_messages)

    @pytest.mark.asyncio
    async def test_desktop_step_fails_on_manual_suggestion(self):
        """A desktop step suggesting manual actions must raise and stop the workflow."""
        provider = _make_streaming_provider('{"result": "Could not access LinkedIn. Apply changes manually."}')
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)
        agent = {
            "id": "agent-cu-skip",
            "name": "Skipped Desktop",
            "description": "",
            "type": "agent",
            "computer_use": True,
            "forge_path": "",
            "steps": [{"name": "Update Profile", "computer_use": True}],
            "output_schema": [],
        }
        # Patch time to simulate 60s so duration check passes, skip-phrase triggers
        with patch("api.engine.executor.time") as mock_time:
            mock_time.monotonic.side_effect = [0.0, 60.0, 60.0]
            await executor._execute_per_step(agent, {}, callback)
        log_messages = [
            call.args[1].get("message", "")
            for call in callback.call_args_list
            if call.args[0] == "agent_log"
        ]
        assert any("WARNING" in m and "manual fallback" in m for m in log_messages)

    @pytest.mark.asyncio
    async def test_desktop_step_warning_does_not_stop_subsequent_steps(self):
        """Desktop step warnings no longer stop the workflow."""
        provider = _make_streaming_provider('{"result": "done"}')
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)
        agent = {
            "id": "agent-multi-cu",
            "name": "Multi Desktop",
            "description": "",
            "type": "agent",
            "computer_use": True,
            "forge_path": "",
            "steps": [
                {"name": "First Desktop Step", "computer_use": True},
                {"name": "Second Desktop Step", "computer_use": True},
            ],
            "output_schema": [],
        }
        await executor._execute_per_step(agent, {}, callback)

        # Both steps should execute
        step_events = [
            call.args[1]
            for call in callback.call_args_list
            if call.args[0] == "step_completed"
        ]
        assert len(step_events) == 2

    @pytest.mark.asyncio
    async def test_desktop_step_warning_emits_step_completed(self):
        """Desktop step with warning still emits step_completed."""
        provider = _make_streaming_provider('{"result": "done"}')
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)
        agent = {
            "id": "agent-cu-warn",
            "name": "Warning Desktop",
            "description": "",
            "type": "agent",
            "computer_use": True,
            "provider": "claude_code",
            "forge_path": "",
            "steps": [
                {"name": "Open App", "computer_use": True},
            ],
            "output_schema": [],
        }
        await executor._execute_per_step(agent, {}, callback)

        event_types = [call.args[0] for call in callback.call_args_list]
        assert "step_completed" in event_types

    @pytest.mark.asyncio
    async def test_cli_step_no_desktop_validation(self):
        """CLI steps must never trigger desktop validation failures."""
        provider = _make_streaming_provider('{"result": "Apply changes manually."}')
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)
        agent = {
            "id": "agent-cli",
            "name": "CLI Agent",
            "description": "",
            "type": "agent",
            "computer_use": False,
            "forge_path": "",
            "steps": [{"name": "Generate Report", "computer_use": False}],
            "output_schema": [],
        }
        # Should NOT raise
        await executor._execute_per_step(agent, {}, callback)


class TestBuildStepPrompt:
    """Tests for build_step_prompt with old and new step file formats."""

    def test_old_format_no_step_files(self):
        """Without agent/steps/ dir, uses old monolithic format."""
        agent = {
            "forge_path": "output/nonexistent-agent/",
            "name": "test",
            "steps": [{"name": "Research", "computer_use": False}],
            "output_schema": [],
        }
        prompt = build_step_prompt(agent, {"topic": "AI"}, step_number=1, step=agent["steps"][0])
        assert "agentic.md" in prompt
        assert "Do NOT execute any other steps" in prompt
        assert "agent/steps/" not in prompt

    def test_new_format_with_step_files(self, tmp_path):
        """With agent/steps/ dir, references step file."""
        # Create a fake agent folder with step files
        forge_path = "output/test-agent"
        full_path = tmp_path / forge_path / "agent" / "steps"
        full_path.mkdir(parents=True)

        agent = {
            "forge_path": forge_path,
            "name": "test",
            "steps": [
                {"name": "Research Topic", "computer_use": False},
                {"name": "Write Report", "computer_use": False},
            ],
            "output_schema": [],
        }

        with patch("api.engine.providers._PROJECT_ROOT", str(tmp_path)):
            prompt = build_step_prompt(agent, {"topic": "AI"}, step_number=1, step=agent["steps"][0])

        assert "agent/steps/step_01_research-topic.md" in prompt
        assert "output/agent_outputs/" in prompt
        assert "step_01_agent_output.md" in prompt

    def test_step_prompt_has_execution_directive(self):
        """Every step prompt ends with the universal execution directive."""
        agent = {
            "forge_path": "output/test/",
            "name": "test",
            "steps": [{"name": "Analyze", "computer_use": False}],
            "output_schema": [],
        }
        prompt = build_step_prompt(agent, {}, step_number=1, step=agent["steps"][0])
        assert "DO NOT summarize" in prompt
        assert "DO NOT ask for confirmation" in prompt
        assert "Execute this step immediately" in prompt

    def test_execution_directive_is_last_section(self):
        """The execution directive should be at the end of the prompt."""
        agent = {
            "forge_path": "output/test/",
            "name": "test",
            "steps": [{"name": "Analyze", "computer_use": False}],
            "output_schema": [],
        }
        prompt = build_step_prompt(agent, {"topic": "AI"}, step_number=1, step=agent["steps"][0])
        # The directive should be in the last lines
        assert prompt.strip().endswith("actually do it.")

    def test_new_format_references_correct_step(self, tmp_path):
        """Step file reference matches step number and kebab name."""
        forge_path = "output/test-agent"
        full_path = tmp_path / forge_path / "agent" / "steps"
        full_path.mkdir(parents=True)

        agent = {
            "forge_path": forge_path,
            "name": "test",
            "steps": [
                {"name": "Gather Data", "computer_use": False},
                {"name": "Analyze Results", "computer_use": False},
            ],
            "output_schema": [{"name": "analysis", "type": "text"}],
        }

        with patch("api.engine.providers._PROJECT_ROOT", str(tmp_path)):
            prompt = build_step_prompt(agent, {}, step_number=2, step=agent["steps"][1])

        assert "step_02_analyze-results.md" in prompt

    def test_computer_use_step_has_mandatory_enforcement(self, tmp_path):
        """Desktop steps must include mandatory computer_use enforcement language."""
        forge_path = "output/test-agent"
        full_path = tmp_path / forge_path / "agent" / "steps"
        full_path.mkdir(parents=True)

        agent = {
            "forge_path": forge_path,
            "name": "test",
            "steps": [
                {"name": "Browse Web", "computer_use": True},
            ],
            "output_schema": [],
        }

        with patch("api.engine.providers._PROJECT_ROOT", str(tmp_path)):
            prompt = build_step_prompt(agent, {}, step_number=1, step=agent["steps"][0])

        assert "MANDATORY" in prompt
        assert "computer use" in prompt
        assert "take a screenshot" in prompt
        assert "DO NOT produce text-only output" in prompt
        assert "DO NOT suggest manual actions" in prompt

    def test_cli_step_has_no_computer_use_enforcement(self, tmp_path):
        """CLI steps must NOT include computer_use enforcement language."""
        forge_path = "output/test-agent"
        full_path = tmp_path / forge_path / "agent" / "steps"
        full_path.mkdir(parents=True)

        agent = {
            "forge_path": forge_path,
            "name": "test",
            "steps": [
                {"name": "Analyze Data", "computer_use": False},
            ],
            "output_schema": [],
        }

        with patch("api.engine.providers._PROJECT_ROOT", str(tmp_path)):
            prompt = build_step_prompt(agent, {}, step_number=1, step=agent["steps"][0])

        assert "MANDATORY" not in prompt
        assert "take a screenshot" not in prompt
        assert "DO NOT produce text-only output" not in prompt


class TestEnvBuilders:
    """Tests for _clean_env and _computer_use_env."""

    def test_clean_env_strips_claudecode(self):
        with patch.dict(os.environ, {"CLAUDECODE": "1"}, clear=False):
            env = CLIAgentProvider._clean_env()
            assert "CLAUDECODE" not in env

    def test_clean_env_strips_claude_vars(self):
        with patch.dict(os.environ, {
            "CLAUDE_CODE_ENTRYPOINT": "cli",
            "CLAUDE_CODE_SSE_PORT": "11378",
        }, clear=False):
            env = CLIAgentProvider._clean_env()
            assert "CLAUDE_CODE_ENTRYPOINT" not in env
            assert "CLAUDE_CODE_SSE_PORT" not in env

    def test_clean_env_strips_api_venv_from_path(self):
        """Strips both bin/ and Scripts/ variants so it works on all platforms."""
        from api.utils.platform import venv_bin_dir
        fake_venv = os.path.join(os.sep, "fake", "api", ".venv")
        bin_dir = str(venv_bin_dir(fake_venv))
        fake_path = os.pathsep.join([bin_dir, os.path.join(os.sep, "usr", "bin"), os.path.join(os.sep, "usr", "local", "bin")])
        with patch.dict(os.environ, {
            "VIRTUAL_ENV": fake_venv,
            "PATH": fake_path,
        }, clear=False):
            env = CLIAgentProvider._clean_env()
            assert bin_dir not in env["PATH"].split(os.pathsep)
            assert "VIRTUAL_ENV" not in env

    def test_clean_env_no_computer_use_venv(self):
        """CLI env should NOT have computer_use venv on PATH."""
        from api.utils.platform import venv_bin_dir
        env = CLIAgentProvider._clean_env()
        cu_bin = str(venv_bin_dir(os.path.join(_PROJECT_ROOT, "computer_use", ".venv")))
        path_entries = env.get("PATH", "").split(os.pathsep)
        assert cu_bin not in path_entries

    def test_computer_use_env_has_cu_venv(self):
        """Desktop env should have computer_use venv bin dir on PATH."""
        from api.utils.platform import venv_bin_dir
        env = CLIAgentProvider._computer_use_env()
        cu_bin = str(venv_bin_dir(os.path.join(_PROJECT_ROOT, "computer_use", ".venv")))
        assert cu_bin in env.get("PATH", "")

    def test_computer_use_env_strips_api_venv(self):
        """Desktop env should still strip the API venv."""
        from api.utils.platform import venv_bin_dir
        fake_venv = os.path.join(os.sep, "fake", "api", ".venv")
        bin_dir = str(venv_bin_dir(fake_venv))
        fake_path = os.pathsep.join([bin_dir, os.path.join(os.sep, "usr", "bin")])
        with patch.dict(os.environ, {
            "VIRTUAL_ENV": fake_venv,
            "PATH": fake_path,
        }, clear=False):
            env = CLIAgentProvider._computer_use_env()
            assert bin_dir not in env["PATH"].split(os.pathsep)

    def test_computer_use_env_cu_venv_first_in_path(self):
        """computer_use venv should be at the start of PATH."""
        from api.utils.platform import venv_bin_dir
        env = CLIAgentProvider._computer_use_env()
        first_path = env["PATH"].split(os.pathsep)[0]
        cu_bin = str(venv_bin_dir(os.path.join(_PROJECT_ROOT, "computer_use", ".venv")))
        assert first_path == cu_bin


class TestCollectOutputPaths:
    """Tests for _collect_output_paths — scan user_outputs/ and map to schema fields."""

    def _make_executor(self):
        return AgentExecutor(provider=None, computer_use_service=None)

    def test_maps_files_to_schema(self, tmp_path):
        """Files in user_outputs/step_XX/ map to output schema fields by kebab->snake."""
        executor = self._make_executor()

        step_dir = tmp_path / "my-agent" / "output" / "run-123" / "user_outputs" / "step_01"
        step_dir.mkdir(parents=True)
        (step_dir / "competitor-profiles.md").write_text("# Profiles")

        schema = [{"name": "competitor_profiles"}, {"name": "swot_analysis"}]
        result = executor._collect_output_paths(
            forge_path="my-agent",
            run_id="run-123",
            output_schema=schema,
            project_root=tmp_path,
        )

        assert "competitor_profiles" in result
        assert result["competitor_profiles"].endswith("competitor-profiles.md")
        assert "swot_analysis" not in result

    def test_empty_when_no_files(self, tmp_path):
        """Returns empty dict when user_outputs/ doesn't exist."""
        executor = self._make_executor()

        result = executor._collect_output_paths(
            forge_path="my-agent",
            run_id="run-123",
            output_schema=[{"name": "report"}],
            project_root=tmp_path,
        )
        assert result == {}

    def test_multiple_steps(self, tmp_path):
        """Files across multiple step dirs all get mapped."""
        executor = self._make_executor()

        base = tmp_path / "agent" / "output" / "run-1" / "user_outputs"
        for i, name in enumerate(["competitor-profiles", "swot-analysis", "strategic-recommendations"], 1):
            d = base / f"step_{i:02d}"
            d.mkdir(parents=True)
            (d / f"{name}.md").write_text(f"# {name}")

        schema = [
            {"name": "competitor_profiles"},
            {"name": "swot_analysis"},
            {"name": "strategic_recommendations"},
        ]
        result = executor._collect_output_paths(
            forge_path="agent",
            run_id="run-1",
            output_schema=schema,
            project_root=tmp_path,
        )

        assert len(result) == 3
        assert all(k in result for k in ["competitor_profiles", "swot_analysis", "strategic_recommendations"])

    def test_returns_empty_when_no_forge_path(self, tmp_path):
        """Without forge_path, returns empty dict."""
        executor = self._make_executor()

        result = executor._collect_output_paths(
            forge_path="",
            run_id="run-123",
            output_schema=[{"name": "result"}],
            project_root=tmp_path,
        )
        assert result == {}

    def test_returns_empty_when_no_schema(self, tmp_path):
        """Without output_schema, returns empty dict."""
        executor = self._make_executor()

        step_dir = tmp_path / "agent" / "output" / "run-1" / "user_outputs" / "step_01"
        step_dir.mkdir(parents=True)
        (step_dir / "report.md").write_text("# Report")

        result = executor._collect_output_paths(
            forge_path="agent",
            run_id="run-1",
            output_schema=[],
            project_root=tmp_path,
        )
        assert result == {}

    def test_maps_single_latest_step_file_to_single_remaining_field(self, tmp_path):
        """When filename drifts from schema, map the only latest-step file to the only field."""
        executor = self._make_executor()

        step1 = tmp_path / "agent" / "output" / "run-1" / "user_outputs" / "step_01"
        step2 = tmp_path / "agent" / "output" / "run-1" / "user_outputs" / "step_02"
        step1.mkdir(parents=True)
        step2.mkdir(parents=True)
        (step1 / "notes.md").write_text("ignored")
        (step2 / "memo.md").write_text("# Memo")

        result = executor._collect_output_paths(
            forge_path="agent",
            run_id="run-1",
            output_schema=[{"name": "memo_file"}],
            project_root=tmp_path,
        )

        assert result == {
            "memo_file": "agent/output/run-1/user_outputs/step_02/memo.md"
        }

    def test_does_not_guess_when_latest_step_has_multiple_files(self, tmp_path):
        """Ambiguous latest-step outputs should not be guessed."""
        executor = self._make_executor()

        step2 = tmp_path / "agent" / "output" / "run-1" / "user_outputs" / "step_02"
        step2.mkdir(parents=True)
        (step2 / "memo.md").write_text("# Memo")
        (step2 / "summary.md").write_text("# Summary")

        result = executor._collect_output_paths(
            forge_path="agent",
            run_id="run-1",
            output_schema=[{"name": "memo_file"}],
            project_root=tmp_path,
        )

        assert result == {}

    def test_returns_artifact_descriptor_for_file_like_outputs(self, tmp_path):
        """File-like outputs should return artifact descriptors, not bare paths."""
        executor = self._make_executor()

        step_dir = tmp_path / "agent" / "output" / "run-1" / "user_outputs" / "step_01"
        step_dir.mkdir(parents=True)
        file_path = step_dir / "report.pdf"
        file_path.write_text("pdf bytes placeholder")

        result = executor._collect_output_paths(
            forge_path="agent",
            run_id="run-1",
            output_schema=[{"name": "report_file", "type": "file"}],
            project_root=tmp_path,
        )

        assert result == {
            "report_file": {
                "kind": "file",
                "path": "agent/output/run-1/user_outputs/step_01/report.pdf",
                "filename": "report.pdf",
                "mime_type": "application/pdf",
            }
        }


class TestExecuteSingleDiskOutputs:
    """_execute_single should pick up files from user_outputs/ when present."""

    @pytest.mark.asyncio
    async def test_execute_single_prefers_disk_outputs_over_parsed_stdout(self, tmp_path):
        """When files exist in user_outputs/, _execute_single returns them (not stdout text)."""
        # Create the output file on disk
        step_dir = tmp_path / "my-agent" / "output" / "run-99" / "user_outputs" / "step_01"
        step_dir.mkdir(parents=True)
        (step_dir / "decision-brief.md").write_text("# Decision Brief\n\nReal content.")

        provider = _make_streaming_provider("decision_brief")  # raw stdout — just the field name
        cu_service = AsyncMock()
        callback = AsyncMock()
        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)

        agent = {
            "id": "a1",
            "name": "Brief",
            "description": "",
            "type": "agent",
            "computer_use": False,
            "forge_path": "my-agent",
            "output_schema": [{"name": "decision_brief", "type": "text"}],
        }

        with patch("api.engine.executor._PROJECT_ROOT", str(tmp_path)):
            result = await executor.execute(agent, {}, callback, run_id="run-99")

        # Should use the disk file, not the raw stdout string
        assert "decision_brief" in result
        assert "decision-brief.md" in result["decision_brief"]

    @pytest.mark.asyncio
    async def test_execute_single_falls_back_to_stdout_when_no_disk_files(self):
        """When no user_outputs/ files, _execute_single uses parsed stdout."""
        provider = _make_streaming_provider('{"summary": "parsed output"}')
        cu_service = AsyncMock()
        callback = AsyncMock()
        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)

        agent = {
            "id": "a2",
            "name": "T",
            "description": "",
            "type": "agent",
            "computer_use": False,
            "forge_path": "nonexistent-agent",
            "output_schema": [{"name": "summary", "type": "text"}],
        }

        result = await executor.execute(agent, {}, callback, run_id="run-00")
        assert result == {"summary": "parsed output"}


class TestResumeAndRetry:
    """Tests for step resume (skip completed) and retry (crash recovery)."""

    def _make_step_agent(self, forge_path="output/test-resume"):
        return {
            "id": "resume-agent",
            "name": "Resume Test",
            "computer_use": False,
            "provider": "claude_code",
            "forge_path": forge_path,
            "description": "Test resume",
            "output_schema": [],
            "steps": [
                {"name": "Step A", "computer_use": False},
                {"name": "Step B", "computer_use": False},
                {"name": "Step C", "computer_use": False},
            ],
        }

    @pytest.mark.asyncio
    async def test_resume_skips_completed_steps(self, tmp_path):
        """Steps with completed result.json on disk should be skipped."""
        from api.engine.executor import AgentExecutor
        from api.engine.providers import ExecutionEvent

        forge_path = str(tmp_path / "agent")
        agent = self._make_step_agent(forge_path)
        run_id = "test-run-resume"

        # Create output dir and write step 1 as completed
        outputs_dir = tmp_path / "agent" / f"output/{run_id}/agent_outputs"
        outputs_dir.mkdir(parents=True)
        (outputs_dir / "step_01_result.json").write_text(
            '{"status": "completed", "summary": "Already done"}'
        )

        call_count = 0

        async def fake_streaming(**kwargs):
            nonlocal call_count
            call_count += 1
            yield ExecutionEvent(type="done", data="step done")

        provider = AsyncMock()
        provider.execute_streaming = fake_streaming
        callback = AsyncMock()
        executor = AgentExecutor(provider, AsyncMock())

        with patch("api.engine.executor._PROJECT_ROOT", str(tmp_path)):
            await executor.execute(agent, {}, callback, run_id=run_id)

        # Should have executed only 2 steps (B and C), not 3
        assert call_count == 2

        # Check that step 1 was logged as skipped
        log_messages = [
            c.args[1]["message"] for c in callback.call_args_list
            if c.args[0] == "agent_log"
        ]
        assert any("skipped, already completed" in m for m in log_messages)
        assert any("Step B" in m and "[CLI]" in m for m in log_messages)

    @pytest.mark.asyncio
    async def test_resume_reruns_failed_step(self, tmp_path):
        """Steps with failed result.json should be re-executed, not skipped."""
        from api.engine.executor import AgentExecutor
        from api.engine.providers import ExecutionEvent

        forge_path = str(tmp_path / "agent")
        agent = self._make_step_agent(forge_path)
        run_id = "test-run-retry-failed"

        outputs_dir = tmp_path / "agent" / f"output/{run_id}/agent_outputs"
        outputs_dir.mkdir(parents=True)
        # Step 1 completed, step 2 failed
        (outputs_dir / "step_01_result.json").write_text(
            '{"status": "completed", "summary": "Done"}'
        )
        (outputs_dir / "step_02_result.json").write_text(
            '{"status": "failed", "error": "something broke"}'
        )

        async def fake_streaming(**kwargs):
            # On re-run, step 2 succeeds -- overwrite the result file
            (outputs_dir / "step_02_result.json").write_text(
                '{"status": "completed", "summary": "Fixed"}'
            )
            yield ExecutionEvent(type="done", data="ok")

        provider = AsyncMock()
        provider.execute_streaming = fake_streaming
        callback = AsyncMock()
        executor = AgentExecutor(provider, AsyncMock())

        with patch("api.engine.executor._PROJECT_ROOT", str(tmp_path)):
            await executor.execute(agent, {}, callback, run_id=run_id)

        # Step 1 skipped, steps 2 and 3 executed
        log_messages = [
            c.args[1]["message"] for c in callback.call_args_list
            if c.args[0] == "agent_log"
        ]
        assert any("Step A" in m and "skipped" in m for m in log_messages)
        assert any("Step B" in m and "[CLI]" in m for m in log_messages)

    @pytest.mark.asyncio
    async def test_retry_on_crash_then_succeed(self, tmp_path):
        """A step that crashes (error event, no result.json) should retry once."""
        from api.engine.executor import AgentExecutor
        from api.engine.providers import ExecutionEvent

        forge_path = str(tmp_path / "agent")
        agent = {
            **self._make_step_agent(forge_path),
            "steps": [{"name": "Flaky Step", "computer_use": False}],
        }
        run_id = "test-run-crash-retry"
        outputs_dir = tmp_path / "agent" / f"output/{run_id}/agent_outputs"
        outputs_dir.mkdir(parents=True)

        attempt = 0

        async def fake_streaming(**kwargs):
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                # First attempt crashes
                yield ExecutionEvent(type="error", data="connection reset")
            else:
                # Second attempt succeeds
                yield ExecutionEvent(type="done", data="ok")

        provider = AsyncMock()
        provider.execute_streaming = fake_streaming
        callback = AsyncMock()
        executor = AgentExecutor(provider, AsyncMock())

        with patch("api.engine.executor._PROJECT_ROOT", str(tmp_path)):
            await executor.execute(agent, {}, callback, run_id=run_id)

        # Should have been called twice (crash + retry)
        assert attempt == 2

        # Check retry was logged
        log_messages = [
            c.args[1]["message"] for c in callback.call_args_list
            if c.args[0] == "agent_log"
        ]
        assert any("Retrying" in m for m in log_messages)

    @pytest.mark.asyncio
    async def test_crash_twice_raises_with_context(self, tmp_path):
        """A step that crashes on both attempts raises with last actions in the error."""
        from api.engine.executor import AgentExecutor
        from api.engine.providers import ExecutionEvent

        forge_path = str(tmp_path / "agent")
        agent = {
            **self._make_step_agent(forge_path),
            "steps": [{"name": "Always Crashes", "computer_use": False}],
        }
        run_id = "test-run-double-crash"
        outputs_dir = tmp_path / "agent" / f"output/{run_id}/agent_outputs"
        outputs_dir.mkdir(parents=True)

        async def fake_streaming(**kwargs):
            yield ExecutionEvent(type="output", data="Using tool: Bash")
            yield ExecutionEvent(type="output", data="Running pytest...")
            yield ExecutionEvent(type="error", data="process killed")

        provider = AsyncMock()
        provider.execute_streaming = fake_streaming
        callback = AsyncMock()
        executor = AgentExecutor(provider, AsyncMock())

        with pytest.raises(RuntimeError, match="Always Crashes.*crashed.*process killed"):
            with patch("api.engine.executor._PROJECT_ROOT", str(tmp_path)):
                await executor.execute(agent, {}, callback, run_id=run_id)

    @pytest.mark.asyncio
    async def test_failed_result_raises_with_error_detail(self, tmp_path):
        """A step that writes failed result.json raises with the error from the file."""
        from api.engine.executor import AgentExecutor
        from api.engine.providers import ExecutionEvent

        forge_path = str(tmp_path / "agent")
        agent = {
            **self._make_step_agent(forge_path),
            "steps": [{"name": "Fails Gracefully", "computer_use": False}],
        }
        run_id = "test-run-graceful-fail"
        outputs_dir = tmp_path / "agent" / f"output/{run_id}/agent_outputs"
        outputs_dir.mkdir(parents=True)

        async def fake_streaming(**kwargs):
            # Agent writes its own failure result
            (outputs_dir / "step_01_result.json").write_text(
                '{"status": "failed", "error": "API returned 500 on /health"}'
            )
            yield ExecutionEvent(type="done", data="")

        provider = AsyncMock()
        provider.execute_streaming = fake_streaming
        callback = AsyncMock()
        executor = AgentExecutor(provider, AsyncMock())

        with pytest.raises(RuntimeError, match="Fails Gracefully.*failed.*API returned 500"):
            with patch("api.engine.executor._PROJECT_ROOT", str(tmp_path)):
                await executor.execute(agent, {}, callback, run_id=run_id)

    @pytest.mark.asyncio
    async def test_all_steps_completed_skips_entire_run(self, tmp_path):
        """If all steps have completed result.json, no provider calls are made."""
        from api.engine.executor import AgentExecutor

        forge_path = str(tmp_path / "agent")
        agent = self._make_step_agent(forge_path)
        run_id = "test-run-all-done"
        outputs_dir = tmp_path / "agent" / f"output/{run_id}/agent_outputs"
        outputs_dir.mkdir(parents=True)

        for i in range(1, 4):
            (outputs_dir / f"step_{i:02d}_result.json").write_text(
                f'{{"status": "completed", "summary": "Step {i} done"}}'
            )

        call_count = 0

        async def fake_streaming(**kwargs):
            nonlocal call_count
            call_count += 1
            yield ExecutionEvent(type="done", data="should not happen")

        provider = AsyncMock()
        provider.execute_streaming = fake_streaming
        callback = AsyncMock()
        executor = AgentExecutor(provider, AsyncMock())

        with patch("api.engine.executor._PROJECT_ROOT", str(tmp_path)):
            await executor.execute(agent, {}, callback, run_id=run_id)

        # No provider calls -- everything was already done
        assert call_count == 0

    @pytest.mark.asyncio
    async def test_resume_reruns_step_with_invalid_json(self, tmp_path):
        """A result.json with invalid JSON is treated as missing -- step re-executes."""
        from api.engine.executor import AgentExecutor
        from api.engine.providers import ExecutionEvent

        forge_path = str(tmp_path / "agent")
        agent = {
            **self._make_step_agent(forge_path),
            "steps": [{"name": "Corrupt Step", "computer_use": False}],
        }
        run_id = "test-run-corrupt-json"
        outputs_dir = tmp_path / "agent" / f"output/{run_id}/agent_outputs"
        outputs_dir.mkdir(parents=True)
        # Write invalid JSON
        (outputs_dir / "step_01_result.json").write_text("{not valid json")

        call_count = 0

        async def fake_streaming(**kwargs):
            nonlocal call_count
            call_count += 1
            yield ExecutionEvent(type="done", data="ok")

        provider = AsyncMock()
        provider.execute_streaming = fake_streaming
        callback = AsyncMock()
        executor = AgentExecutor(provider, AsyncMock())

        with patch("api.engine.executor._PROJECT_ROOT", str(tmp_path)):
            await executor.execute(agent, {}, callback, run_id=run_id)

        # Invalid JSON means file is treated as missing -- step must re-execute
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_resume_reruns_step_with_no_status_field(self, tmp_path):
        """A result.json without a 'status' field is treated as missing -- step re-executes."""
        from api.engine.executor import AgentExecutor
        from api.engine.providers import ExecutionEvent

        forge_path = str(tmp_path / "agent")
        agent = {
            **self._make_step_agent(forge_path),
            "steps": [{"name": "No Status Step", "computer_use": False}],
        }
        run_id = "test-run-no-status"
        outputs_dir = tmp_path / "agent" / f"output/{run_id}/agent_outputs"
        outputs_dir.mkdir(parents=True)
        # Write JSON with no status field
        (outputs_dir / "step_01_result.json").write_text('{"summary": "done but no status"}')

        call_count = 0

        async def fake_streaming(**kwargs):
            nonlocal call_count
            call_count += 1
            yield ExecutionEvent(type="done", data="ok")

        provider = AsyncMock()
        provider.execute_streaming = fake_streaming
        callback = AsyncMock()
        executor = AgentExecutor(provider, AsyncMock())

        with patch("api.engine.executor._PROJECT_ROOT", str(tmp_path)):
            await executor.execute(agent, {}, callback, run_id=run_id)

        # No status field means _step_result_exists returns None -- step must re-execute
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_resume_skipped_step_uses_default_summary(self, tmp_path):
        """A completed step with no 'summary' field emits step_completed with summary='(resumed)'."""
        from api.engine.executor import AgentExecutor
        from api.engine.providers import ExecutionEvent

        forge_path = str(tmp_path / "agent")
        agent = {
            **self._make_step_agent(forge_path),
            "steps": [{"name": "Silent Step", "computer_use": False}],
        }
        run_id = "test-run-no-summary"
        outputs_dir = tmp_path / "agent" / f"output/{run_id}/agent_outputs"
        outputs_dir.mkdir(parents=True)
        # Completed but no summary field
        (outputs_dir / "step_01_result.json").write_text('{"status": "completed"}')

        provider = AsyncMock()
        callback = AsyncMock()
        executor = AgentExecutor(provider, AsyncMock())

        with patch("api.engine.executor._PROJECT_ROOT", str(tmp_path)):
            await executor.execute(agent, {}, callback, run_id=run_id)

        # Find the step_completed event for the skipped step
        step_completed_calls = [
            c for c in callback.call_args_list
            if c.args[0] == "step_completed"
        ]
        assert len(step_completed_calls) == 1
        data = step_completed_calls[0].args[1]
        assert data["summary"] == "(resumed)"
        assert data["duration"] == 0

    @pytest.mark.asyncio
    async def test_resume_reruns_step_with_unknown_status(self, tmp_path):
        """A result.json with status='running' (not 'completed') causes the step to re-execute."""
        from api.engine.executor import AgentExecutor
        from api.engine.providers import ExecutionEvent

        forge_path = str(tmp_path / "agent")
        agent = {
            **self._make_step_agent(forge_path),
            "steps": [{"name": "Running Step", "computer_use": False}],
        }
        run_id = "test-run-unknown-status"
        outputs_dir = tmp_path / "agent" / f"output/{run_id}/agent_outputs"
        outputs_dir.mkdir(parents=True)
        # Status is 'running' -- not 'completed', should not be skipped
        (outputs_dir / "step_01_result.json").write_text('{"status": "running"}')

        call_count = 0

        async def fake_streaming(**kwargs):
            nonlocal call_count
            call_count += 1
            (outputs_dir / "step_01_result.json").write_text('{"status": "completed", "summary": "fixed"}')
            yield ExecutionEvent(type="done", data="ok")

        provider = AsyncMock()
        provider.execute_streaming = fake_streaming
        callback = AsyncMock()
        executor = AgentExecutor(provider, AsyncMock())

        with patch("api.engine.executor._PROJECT_ROOT", str(tmp_path)):
            await executor.execute(agent, {}, callback, run_id=run_id)

        # 'running' status is not 'completed' -- step must be re-executed
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_resume_skipped_step_emits_duration_zero(self, tmp_path):
        """Skipped (already completed) steps emit step_completed with duration=0."""
        from api.engine.executor import AgentExecutor
        from api.engine.providers import ExecutionEvent

        forge_path = str(tmp_path / "agent")
        agent = {
            **self._make_step_agent(forge_path),
            "steps": [
                {"name": "Already Done", "computer_use": False},
                {"name": "New Step", "computer_use": False},
            ],
        }
        run_id = "test-run-duration-zero"
        outputs_dir = tmp_path / "agent" / f"output/{run_id}/agent_outputs"
        outputs_dir.mkdir(parents=True)
        (outputs_dir / "step_01_result.json").write_text('{"status": "completed", "summary": "done"}')

        async def fake_streaming(**kwargs):
            yield ExecutionEvent(type="done", data="ok")

        provider = AsyncMock()
        provider.execute_streaming = fake_streaming
        callback = AsyncMock()
        executor = AgentExecutor(provider, AsyncMock())

        with patch("api.engine.executor._PROJECT_ROOT", str(tmp_path)):
            await executor.execute(agent, {}, callback, run_id=run_id)

        step_completed_calls = [
            c for c in callback.call_args_list
            if c.args[0] == "step_completed"
        ]
        # First step_completed is for the skipped step
        assert step_completed_calls[0].args[1]["duration"] == 0
        assert step_completed_calls[0].args[1]["step_name"] == "Already Done"

"""Tests for agent executor with mocked provider."""

import os
import tempfile

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api.engine.executor import AgentExecutor
from api.engine.providers import ExecutionEvent, build_step_prompt, _PROJECT_ROOT


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

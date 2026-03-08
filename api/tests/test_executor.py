"""Tests for agent executor with mocked provider."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from api.engine.executor import AgentExecutor


class TestAgentExecutor:

    @pytest.mark.asyncio
    async def test_execute_simple_agent(self):
        provider = AsyncMock()
        provider.execute.return_value = '{"findings": "AI safety research data"}'
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
        provider.execute.assert_called_once()

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
        provider.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_emits_agent_started_and_completed(self):
        provider = AsyncMock()
        provider.execute.return_value = '{"out": "val"}'
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
        provider = AsyncMock()
        provider.execute.side_effect = RuntimeError("Provider down")
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
        provider = AsyncMock()
        provider.execute.return_value = '{"article": "Full article..."}'
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
        provider.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_parses_non_json_output(self):
        """When provider returns plain text, maps to first output field."""
        provider = AsyncMock()
        provider.execute.return_value = "Just some plain text output"
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
    async def test_execute_with_forge_path(self):
        """When agent has forge_path, prompt references agentic.md."""
        provider = AsyncMock()
        provider.execute.return_value = '{"result": "done"}'
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

        call_args = provider.execute.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        assert "agentic.md" in prompt

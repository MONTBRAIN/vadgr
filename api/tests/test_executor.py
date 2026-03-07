"""Tests for task executor with mocked LLM."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from api.engine.executor import TaskExecutor


class TestTaskExecutor:

    @pytest.mark.asyncio
    async def test_execute_simple_task(self):
        llm_service = AsyncMock()
        llm_service.call.return_value = {"findings": "AI safety research data"}
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = TaskExecutor(llm_service=llm_service, computer_use_service=cu_service)
        task = {
            "id": "task-1",
            "name": "Research",
            "description": "Research a topic",
            "type": "task",
            "computer_use": False,
            "forge_config": {"complexity": "simple", "agents": 1, "steps": 1},
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "input_schema": [{"name": "topic", "type": "text", "required": True}],
            "output_schema": [{"name": "findings", "type": "text"}],
        }
        inputs = {"topic": "AI Safety"}
        result = await executor.execute(task, inputs, callback)
        assert result == {"findings": "AI safety research data"}
        llm_service.call.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_computer_use_task(self):
        llm_service = AsyncMock()
        cu_service = AsyncMock()
        cu_service.run_task.return_value = {"screenshot": "base64...", "success": True}
        callback = AsyncMock()

        executor = TaskExecutor(llm_service=llm_service, computer_use_service=cu_service)
        task = {
            "id": "task-2",
            "name": "Fill Form",
            "description": "Fill a form on the web",
            "type": "task",
            "computer_use": True,
            "forge_config": {},
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "input_schema": [],
            "output_schema": [],
        }
        result = await executor.execute(task, {}, callback)
        assert result["success"] is True
        cu_service.run_task.assert_called_once()
        llm_service.call.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_emits_task_started_and_completed(self):
        llm_service = AsyncMock()
        llm_service.call.return_value = {"out": "val"}
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = TaskExecutor(llm_service=llm_service, computer_use_service=cu_service)
        task = {
            "id": "task-3",
            "name": "T",
            "description": "",
            "type": "task",
            "computer_use": False,
            "forge_config": {"complexity": "simple"},
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "input_schema": [],
            "output_schema": [],
        }
        await executor.execute(task, {}, callback)

        event_types = [call.args[0] for call in callback.call_args_list]
        assert "task_started" in event_types
        assert "task_completed" in event_types

    @pytest.mark.asyncio
    async def test_execute_emits_task_failed_on_error(self):
        llm_service = AsyncMock()
        llm_service.call.side_effect = RuntimeError("LLM down")
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = TaskExecutor(llm_service=llm_service, computer_use_service=cu_service)
        task = {
            "id": "task-4",
            "name": "T",
            "description": "",
            "type": "task",
            "computer_use": False,
            "forge_config": {},
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "input_schema": [],
            "output_schema": [],
        }
        with pytest.raises(RuntimeError):
            await executor.execute(task, {}, callback)

        event_types = [call.args[0] for call in callback.call_args_list]
        assert "task_failed" in event_types

    @pytest.mark.asyncio
    async def test_execute_multi_step_task(self):
        """Multi-step tasks still go through LLM service (forge handles internally)."""
        llm_service = AsyncMock()
        llm_service.call.return_value = {"article": "Full article..."}
        cu_service = AsyncMock()
        callback = AsyncMock()

        executor = TaskExecutor(llm_service=llm_service, computer_use_service=cu_service)
        task = {
            "id": "task-5",
            "name": "Write Paper",
            "description": "Write a research paper",
            "type": "task",
            "computer_use": False,
            "forge_config": {"complexity": "multi_step", "agents": 3, "steps": 5},
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "input_schema": [],
            "output_schema": [],
        }
        result = await executor.execute(task, {"topic": "AI"}, callback)
        assert result == {"article": "Full article..."}
        llm_service.call.assert_called_once()

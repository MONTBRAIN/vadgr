"""Tests for service layer."""

import pytest
from unittest.mock import AsyncMock, patch

from api.services.llm_service import LLMService
from api.services.computer_use_service import ComputerUseService
from api.services.execution_service import ExecutionService


class TestLLMService:

    @pytest.mark.asyncio
    async def test_call_builds_prompt_from_task(self):
        service = LLMService()
        with patch.object(service, "_call_provider", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = "Research findings about AI safety"
            task = {
                "id": "t1",
                "name": "Research",
                "description": "Research a topic",
                "forge_config": {"complexity": "simple"},
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "output_schema": [{"name": "findings", "type": "text"}],
            }
            result = await service.call(task, {"topic": "AI Safety"})
            mock_call.assert_called_once()
            assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_call_returns_dict_with_output_fields(self):
        service = LLMService()
        with patch.object(service, "_call_provider", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = "Some output text"
            task = {
                "id": "t1",
                "name": "T",
                "description": "desc",
                "forge_config": {},
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "output_schema": [
                    {"name": "result", "type": "text"},
                    {"name": "score", "type": "number"},
                ],
            }
            result = await service.call(task, {})
            assert "result" in result


class TestComputerUseService:

    @pytest.mark.asyncio
    async def test_run_task_delegates_to_engine(self):
        service = ComputerUseService()
        service._engine = AsyncMock()
        service._engine.run_task = AsyncMock(return_value={
            "success": True, "screenshot": "base64..."
        })
        callback = AsyncMock()

        task = {"id": "t1", "name": "Fill Form", "description": "Fill web form"}
        result = await service.run_task(task, {"url": "http://example.com"}, callback)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_run_task_returns_failure_when_engine_unavailable(self):
        service = ComputerUseService()
        service._engine = None
        callback = AsyncMock()

        task = {"id": "t1", "name": "T", "description": ""}
        result = await service.run_task(task, {}, callback)
        assert result["success"] is False


class TestExecutionService:

    @pytest.mark.asyncio
    async def test_run_standalone_task(self, db):
        from api.persistence.repositories import TaskRepository, RunRepository
        task_repo = TaskRepository(db)
        run_repo = RunRepository(db)

        task = await task_repo.create(
            name="Research", description="Research a topic",
            input_schema=[{"name": "topic", "type": "text", "required": True}],
            output_schema=[{"name": "findings", "type": "text"}],
        )
        run = await run_repo.create(task_id=task["id"], inputs={"topic": "AI"})

        executor_mock = AsyncMock()
        executor_mock.execute.return_value = {"findings": "AI research data"}
        emit_mock = AsyncMock()

        service = ExecutionService(
            task_repo=task_repo,
            run_repo=run_repo,
            project_repo=None,
            executor=executor_mock,
            emit=emit_mock,
        )
        await service.run_standalone_task(run["id"])

        updated_run = await run_repo.get(run["id"])
        assert updated_run["status"] == "completed"
        assert updated_run["outputs"] == {"findings": "AI research data"}
        emit_mock.assert_any_call(run["id"], "run_started", {})
        emit_mock.assert_any_call(
            run["id"], "run_completed",
            {"outputs": {"findings": "AI research data"}},
        )

    @pytest.mark.asyncio
    async def test_run_standalone_task_failure(self, db):
        from api.persistence.repositories import TaskRepository, RunRepository
        task_repo = TaskRepository(db)
        run_repo = RunRepository(db)

        task = await task_repo.create(name="T", description="")
        run = await run_repo.create(task_id=task["id"])

        executor_mock = AsyncMock()
        executor_mock.execute.side_effect = RuntimeError("boom")
        emit_mock = AsyncMock()

        service = ExecutionService(
            task_repo=task_repo,
            run_repo=run_repo,
            project_repo=None,
            executor=executor_mock,
            emit=emit_mock,
        )
        await service.run_standalone_task(run["id"])

        updated_run = await run_repo.get(run["id"])
        assert updated_run["status"] == "failed"

    @pytest.mark.asyncio
    async def test_run_project_dag(self, db):
        from api.persistence.repositories import (
            TaskRepository, ProjectRepository, RunRepository,
        )
        task_repo = TaskRepository(db)
        project_repo = ProjectRepository(db)
        run_repo = RunRepository(db)

        t1 = await task_repo.create(
            name="Research", description="Research",
            input_schema=[{"name": "topic", "type": "text", "required": True}],
            output_schema=[{"name": "findings", "type": "text"}],
        )
        t2 = await task_repo.create(
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
        async def mock_execute(task, inputs, callback):
            nonlocal call_count
            call_count += 1
            if task["name"] == "Research":
                return {"findings": "AI data"}
            return {"article": "Full article about AI"}

        executor_mock = AsyncMock()
        executor_mock.execute = mock_execute
        emit_mock = AsyncMock()

        service = ExecutionService(
            task_repo=task_repo,
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
            TaskRepository, ProjectRepository, RunRepository,
        )
        task_repo = TaskRepository(db)
        project_repo = ProjectRepository(db)
        run_repo = RunRepository(db)

        t1 = await task_repo.create(name="Work", description="Do work",
            output_schema=[{"name": "result", "type": "text"}])
        t_gate = await task_repo.create(name="Gate", description="", type="approval")
        project = await project_repo.create(name="P", description="")
        n1 = await project_repo.add_node(project["id"], t1["id"])
        n_gate = await project_repo.add_node(project["id"], t_gate["id"])
        await project_repo.add_edge(
            project["id"], n1["id"], n_gate["id"],
            source_output="result", target_input="in",
        )
        run = await run_repo.create(project_id=project["id"])

        async def mock_execute(task, inputs, callback):
            return {"result": "done"}

        executor_mock = AsyncMock()
        executor_mock.execute = mock_execute
        emit_mock = AsyncMock()

        service = ExecutionService(
            task_repo=task_repo,
            run_repo=run_repo,
            project_repo=project_repo,
            executor=executor_mock,
            emit=emit_mock,
        )
        await service.run_project(run["id"])

        updated_run = await run_repo.get(run["id"])
        assert updated_run["status"] == "awaiting_approval"
        # Find the approval_required emit call and check its data
        approval_calls = [
            c for c in emit_mock.call_args_list
            if c.args[1] == "approval_required"
        ]
        assert len(approval_calls) == 1
        data = approval_calls[0].args[2]
        assert data["node_id"] == n_gate["id"]
        assert n1["id"] in data["outputs_so_far"]
        assert data["outputs_so_far"][n1["id"]] == {"result": "done"}

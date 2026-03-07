"""Shared test fixtures."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.persistence.database import Database
from api.persistence.repositories import TaskRepository, ProjectRepository, RunRepository
from api.main import create_app


@pytest.fixture
def make_node():
    """Factory for creating ProjectNode dicts for DAG tests."""
    def _make(node_id, task_id=None, task_type="task"):
        return {
            "id": node_id,
            "project_id": "proj-1",
            "task_id": task_id or f"task-{node_id}",
            "task_type": task_type,
            "config": {},
            "position_x": 0.0,
            "position_y": 0.0,
        }
    return _make


@pytest.fixture
def make_edge():
    """Factory for creating ProjectEdge dicts for DAG tests."""
    def _make(source_id, target_id, source_output="out", target_input="in"):
        return {
            "id": f"edge-{source_id}-{target_id}",
            "project_id": "proj-1",
            "source_node_id": source_id,
            "target_node_id": target_id,
            "source_output": source_output,
            "target_input": target_input,
        }
    return _make


@pytest_asyncio.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    await database.create_tables()
    yield database
    await database.disconnect()


@pytest_asyncio.fixture
async def app(db):
    application = create_app(db)
    # Manually set state since httpx ASGITransport doesn't run lifespan
    application.state.db = db
    application.state.task_repo = TaskRepository(db)
    application.state.project_repo = ProjectRepository(db)
    application.state.run_repo = RunRepository(db)
    from api.websocket.manager import ConnectionManager
    from api.engine.executor import TaskExecutor
    from api.services.llm_service import LLMService
    from api.services.computer_use_service import ComputerUseService
    from api.services.execution_service import ExecutionService
    from unittest.mock import AsyncMock

    application.state.ws_manager = ConnectionManager()

    llm_service = LLMService()
    cu_service = ComputerUseService()
    executor = TaskExecutor(llm_service=llm_service, computer_use_service=cu_service)

    async def emit(run_id, event_type, data):
        await application.state.ws_manager.emit(run_id, event_type, data)

    application.state.execution_service = ExecutionService(
        task_repo=application.state.task_repo,
        run_repo=application.state.run_repo,
        project_repo=application.state.project_repo,
        executor=executor,
        emit=emit,
    )
    yield application


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

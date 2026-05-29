"""Shared test fixtures."""

import asyncio
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.persistence.database import Database
from api.persistence.repositories import (
    AgentRepository,
    DeviceRepository,
    ProjectRepository,
    RunRepository,
)
from api.main import create_app
from api.auth.pairing import PairingStore
from api.auth import tokens as auth_tokens


@pytest.fixture
def make_node():
    """Factory for creating ProjectNode dicts for DAG tests."""
    def _make(node_id, agent_id=None, agent_type="agent"):
        return {
            "id": node_id,
            "project_id": "proj-1",
            "agent_id": agent_id or f"agent-{node_id}",
            "agent_type": agent_type,
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
    application.state.agent_repo = AgentRepository(db)
    application.state.project_repo = ProjectRepository(db)
    application.state.run_repo = RunRepository(db)
    application.state.device_repo = DeviceRepository(db)
    application.state.pairing_store = PairingStore()
    auth_tokens.reset_for_tests()
    from api.websocket.manager import ConnectionManager
    from api.engine.executor import AgentExecutor
    from api.engine.providers import CLIAgentProvider, ProviderConfig
    from api.services.computer_use_service import ComputerUseService
    from api.services.agent_service import AgentService
    from api.services.artifact_service import ArtifactService
    from api.services.execution_service import ExecutionService
    from unittest.mock import AsyncMock

    application.state.ws_manager = ConnectionManager()
    application.state.artifact_service = ArtifactService(Path(__file__).resolve().parent.parent)

    provider = AsyncMock(spec=CLIAgentProvider)
    # Return valid forge JSON so background run_forge succeeds in tests
    import json
    provider.execute.return_value = json.dumps({
        "forge_path": "output/test-agent/",
        "forge_config": {"complexity": "simple", "steps": 1, "prompts": ["01_Agent.md"]},
        "input_schema": [],
        "output_schema": [],
    })
    agent_service = AgentService(
        agent_repo=application.state.agent_repo,
        provider=provider,
    )
    # Stub out run_forge and run_update so background tasks created by
    # POST/PUT /api/agents don't perform real disk I/O (git init, venv
    # creation, etc.).  Without this, 50+ background tasks pile up and
    # the event loop never drains, causing the suite to hang.
    _original_run_forge = agent_service.run_forge

    async def _fast_run_forge(agent_id: str) -> None:
        agent = await agent_service.agent_repo.get(agent_id)
        if agent:
            await agent_service.agent_repo.update(agent_id, status="ready")

    agent_service.run_forge = _fast_run_forge
    agent_service.run_update = AsyncMock()
    application.state.agent_service = agent_service
    cu_service = ComputerUseService()
    executor = AgentExecutor(provider=provider, computer_use_service=cu_service)

    async def emit(run_id, event_type, data):
        await application.state.ws_manager.emit(run_id, event_type, data)

    application.state.execution_service = ExecutionService(
        agent_repo=application.state.agent_repo,
        run_repo=application.state.run_repo,
        project_repo=application.state.project_repo,
        executor=executor,
        emit=emit,
        provider_factory=AsyncMock(return_value=provider),
    )
    application.state.active_run_tasks: dict[str, asyncio.Task] = {}
    yield application
    # Cancel any run tasks that outlived the test so they don't hit the closed DB
    tasks = list(application.state.active_run_tasks.values())
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

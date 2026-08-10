"""Shared test fixtures."""

import asyncio

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.persistence.database import Database
from api.persistence.repositories import RunRepository
from api.main import create_app


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
    application.state.run_repo = RunRepository(db)
    from api.auth.devices import DeviceRepository
    from api.auth.pairing_store import PairingStore
    from api.transport import LoopbackTransport
    application.state.device_repo = DeviceRepository(db)
    application.state.pairing_store = PairingStore()
    application.state.transport = LoopbackTransport()
    from api.websocket.manager import ConnectionManager
    from api.engine.providers import CLIAgentProvider
    from api.services.execution_service import ExecutionService
    from unittest.mock import AsyncMock

    application.state.ws_manager = ConnectionManager()

    provider = AsyncMock(spec=CLIAgentProvider)

    async def emit(run_id, event_type, data):
        await application.state.ws_manager.emit(run_id, event_type, data)

    execution_service = ExecutionService(
        run_repo=application.state.run_repo,
        emit=emit,
        provider_factory=AsyncMock(return_value=provider),
    )
    # The route tests are about the route: what it writes, what it answers, and
    # what it registers for cancel. Driving a real provider from here would put
    # the machine's configured loop behind every one of them. The service's own
    # behaviour is tested directly, and through HTTP in test_run_trigger.py.
    execution_service.start_run = AsyncMock()
    execution_service.resume_run = AsyncMock()
    application.state.execution_service = execution_service
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

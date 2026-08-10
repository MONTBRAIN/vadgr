"""FastAPI application factory."""

import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI

from api.config import settings
from api.persistence.database import Database
from api.persistence.repositories import RunRepository
from api.auth.devices import DeviceRepository
from api.auth.pairing_store import PairingStore
from api.auth.middleware import TwoGateMiddleware
from api.transport import create_transport
from api.websocket.manager import ConnectionManager
from api.websocket.events import make_event
from api.engine.providers import create_provider
from api.services.execution_service import ExecutionService
from api.routes import health, runs, computer_use, providers, ws
from api.routes import auth as auth_routes
from api.routes import devices as devices_routes
from api.routes import settings as settings_routes

logger = logging.getLogger(__name__)


def create_app(db: Optional[Database] = None, transport=None) -> FastAPI:
    """Create the FastAPI app. Pass a Database for testing (in-memory) and an
    optional ``transport`` (a ``TransportProvider``); defaults to the configured
    transport via ``VADGR_TRANSPORT``."""
    transport = transport or create_transport()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if db:
            app.state.db = db
        else:
            Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
            app.state.db = Database(settings.database_path)
            await app.state.db.connect()
            await app.state.db.create_tables()

        # Continue anything the last process died inside, before serving. A
        # journal ending in a dangling in_flight is the only durable evidence a
        # run was interrupted, and nothing else in the system looks for one.
        try:
            from api.services.execution_service import resume_interrupted_runs

            resumed = await resume_interrupted_runs()
            if resumed:
                logger.info("resumed %d interrupted run(s): %s", len(resumed), resumed)
        except Exception:
            # A daemon that cannot resume must still boot: an unreadable journal
            # is a reason to serve without it, not a reason to be down.
            logger.exception("resume on boot failed; continuing without it")

        app.state.run_repo = RunRepository(app.state.db)
        app.state.device_repo = DeviceRepository(app.state.db)
        app.state.pairing_store = PairingStore()
        app.state.transport = transport
        app.state.ws_manager = ConnectionManager()
        app.state.active_run_tasks: dict[str, asyncio.Task] = {}

        async def emit(run_id, event_type, data):
            await app.state.ws_manager.broadcast_event(run_id, make_event(event_type, data))

        app.state.execution_service = ExecutionService(
            run_repo=app.state.run_repo,
            emit=emit,
            provider_factory=create_provider,
        )
        yield
        if not db:
            await app.state.db.disconnect()

    app = FastAPI(title="Vadgr API", version=settings.version, lifespan=lifespan)
    app.state.transport = transport

    # No CORS layer: the only clients are the CLI on the box and the phone
    # over the tailnet, neither of which is a browser sending an Origin.
    app.add_middleware(TwoGateMiddleware, transport=transport)

    app.include_router(health.router)
    app.include_router(runs.router)
    app.include_router(computer_use.router)
    app.include_router(providers.router)
    app.include_router(auth_routes.router)
    app.include_router(devices_routes.router)
    app.include_router(settings_routes.router)
    app.include_router(ws.router)

    return app


app = create_app()

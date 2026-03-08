"""FastAPI application factory."""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.persistence.database import Database
from api.persistence.repositories import AgentRepository, ProjectRepository, RunRepository
from api.websocket.manager import ConnectionManager
from api.engine.executor import AgentExecutor
from api.engine.providers import CLIAgentProvider, load_provider_config
from api.services.computer_use_service import ComputerUseService
from api.services.agent_service import AgentService
from api.services.execution_service import ExecutionService
from api.routes import health, agents, projects, runs, computer_use, ws


def create_app(db: Optional[Database] = None) -> FastAPI:
    """Create the FastAPI app. Pass a Database for testing (in-memory)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if db:
            app.state.db = db
        else:
            app.state.db = Database(settings.database_path)
            await app.state.db.connect()
            await app.state.db.create_tables()

        app.state.agent_repo = AgentRepository(app.state.db)
        app.state.project_repo = ProjectRepository(app.state.db)
        app.state.run_repo = RunRepository(app.state.db)
        app.state.ws_manager = ConnectionManager()

        provider_config = load_provider_config(
            settings.default_provider,
            {"timeout": settings.provider_timeout},
        )
        provider = CLIAgentProvider(provider_config)
        cu_service = ComputerUseService()
        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)

        async def emit(run_id, event_type, data):
            await app.state.ws_manager.emit(run_id, event_type, data)

        app.state.agent_service = AgentService(
            agent_repo=app.state.agent_repo,
            provider=provider,
        )

        app.state.execution_service = ExecutionService(
            agent_repo=app.state.agent_repo,
            run_repo=app.state.run_repo,
            project_repo=app.state.project_repo,
            executor=executor,
            emit=emit,
        )
        yield
        if not db:
            await app.state.db.disconnect()

    app = FastAPI(title="Agent Forge API", version=settings.version, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(agents.router)
    app.include_router(projects.router)
    app.include_router(runs.router)
    app.include_router(computer_use.router)
    app.include_router(ws.router)

    return app


app = create_app()

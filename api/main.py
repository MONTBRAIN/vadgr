"""FastAPI application factory."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.persistence.database import Database
from api.persistence.repositories import AgentRepository, ProjectRepository, RunRepository
from api.websocket.manager import ConnectionManager
from api.websocket.events import make_event
from api.engine.executor import AgentExecutor
from api.engine.providers import CLIAgentProvider, create_provider, load_provider_config
from api.services.computer_use_service import ComputerUseService
from api.services.agent_service import AgentService
from api.services.artifact_service import ArtifactService
from api.services.execution_service import ExecutionService
from api.services.log_writer import LogWriter
from api.routes import health, agents, projects, runs, computer_use, providers, ws


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
        app.state.artifact_service = ArtifactService(Path(__file__).resolve().parent.parent)
        app.state.active_run_tasks: dict[str, asyncio.Task] = {}

        provider_config = load_provider_config(
            settings.default_provider,
            {"timeout": settings.provider_timeout},
        )
        provider = CLIAgentProvider(provider_config)
        cu_service = ComputerUseService()
        executor = AgentExecutor(provider=provider, computer_use_service=cu_service)

        log_writer = LogWriter(Path(__file__).resolve().parent.parent)
        _log_path_set: set[str] = set()
        _run_forge_paths: dict[str, str] = {}

        # Run-level event types go to execution.jsonl; step-level go to step files
        _run_level_events = {"run_started", "run_completed", "run_failed", "approval_required"}

        async def emit(run_id, event_type, data):
            event = make_event(event_type, data)

            # Cache forge_path from run_started event
            if event_type == "run_started" and data and data.get("forge_path"):
                _run_forge_paths[run_id] = data["forge_path"]

            forge_path = _run_forge_paths.get(run_id, "")

            # Persist to JSONL
            if event_type in _run_level_events:
                log_writer.append_run_event(run_id, event, forge_path=forge_path)
            elif data and data.get("step_num"):
                log_writer.append_step_event(
                    run_id, data["step_num"], data["step_name"], event,
                    forge_path=forge_path,
                )
            else:
                # Single-step agent events go to execution.jsonl as well
                log_writer.append_run_event(run_id, event, forge_path=forge_path)

            # Set log_path on first event per run
            if run_id not in _log_path_set:
                if forge_path:
                    log_path = f"{forge_path}/output/{run_id}/agent_logs"
                else:
                    log_path = f"output/{run_id}/agent_logs"
                await app.state.run_repo.set_log_path(run_id, log_path)
                _log_path_set.add(run_id)

            # Broadcast via WebSocket
            await app.state.ws_manager.broadcast_event(run_id, event)

        app.state.agent_service = AgentService(
            agent_repo=app.state.agent_repo,
            provider=provider,
            provider_factory=create_provider,
        )

        app.state.execution_service = ExecutionService(
            agent_repo=app.state.agent_repo,
            run_repo=app.state.run_repo,
            project_repo=app.state.project_repo,
            executor=executor,
            emit=emit,
            provider_factory=create_provider,
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
    app.include_router(providers.router)
    app.include_router(ws.router)

    return app


app = create_app()

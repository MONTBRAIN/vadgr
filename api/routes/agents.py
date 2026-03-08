"""Agent CRUD routes."""

import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from api.models.agent import AgentCreate, AgentUpdate, AgentRunRequest

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _not_found(agent_id: str):
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "AGENT_NOT_FOUND", "message": f"Agent with id '{agent_id}' not found", "details": {}}},
    )


@router.post("", status_code=201)
async def create_agent(body: AgentCreate, request: Request, background_tasks: BackgroundTasks):
    agent_service = request.app.state.agent_service
    agent = await agent_service.create_agent(
        name=body.name,
        description=body.description,
        steps=body.steps,
        samples=body.samples,
        computer_use=body.computer_use,
        provider=body.provider,
        model=body.model,
    )
    # Trigger forge generation in the background
    background_tasks.add_task(agent_service.run_forge, agent["id"])
    return agent


@router.get("")
async def list_agents(request: Request):
    repo = request.app.state.agent_repo
    return await repo.list_all()


@router.get("/{agent_id}")
async def get_agent(agent_id: str, request: Request):
    repo = request.app.state.agent_repo
    agent = await repo.get(agent_id)
    if not agent:
        return _not_found(agent_id)
    return agent


_SUBSTANTIVE_FIELDS = {"description", "steps", "samples", "computer_use"}


@router.put("/{agent_id}")
async def update_agent(
    agent_id: str, body: AgentUpdate, request: Request,
    background_tasks: BackgroundTasks,
):
    repo = request.app.state.agent_repo
    agent_service = request.app.state.agent_service

    fields = body.model_dump(exclude_none=True)
    if "input_schema" in fields:
        fields["input_schema"] = [s.model_dump() if hasattr(s, "model_dump") else s for s in fields["input_schema"]]
    if "output_schema" in fields:
        fields["output_schema"] = [s.model_dump() if hasattr(s, "model_dump") else s for s in fields["output_schema"]]

    substantive_changes = _SUBSTANTIVE_FIELDS & fields.keys()

    # If substantive change, check agent isn't busy
    if substantive_changes:
        current = await repo.get(agent_id)
        if not current:
            return _not_found(agent_id)
        if current["status"] in ("creating", "updating"):
            return JSONResponse(
                status_code=409,
                content={"error": {"code": "AGENT_BUSY", "message": f"Agent is '{current['status']}', cannot update substantive fields now", "details": {}}},
            )
        # Set status to updating and trigger forge
        fields["status"] = "updating"
        agent = await repo.update(agent_id, **fields)
        if not agent:
            return _not_found(agent_id)
        background_tasks.add_task(
            agent_service.run_update, agent_id, current, fields,
        )
        return agent

    # Cosmetic update only
    agent = await repo.update(agent_id, **fields)
    if not agent:
        return _not_found(agent_id)
    return agent


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: str, request: Request):
    repo = request.app.state.agent_repo
    agent = await repo.get(agent_id)
    if not agent:
        return _not_found(agent_id)
    # Clean up the output folder if it exists
    forge_path = agent.get("forge_path", "")
    if forge_path:
        path = Path(forge_path)
        if path.exists() and path.is_dir():
            shutil.rmtree(path)
    await repo.delete(agent_id)


@router.post("/{agent_id}/run", status_code=202)
async def run_agent(agent_id: str, body: AgentRunRequest, request: Request, background_tasks: BackgroundTasks):
    agent_repo = request.app.state.agent_repo
    run_repo = request.app.state.run_repo
    execution_service = request.app.state.execution_service

    agent = await agent_repo.get(agent_id)
    if not agent:
        return _not_found(agent_id)

    if agent["status"] != "ready":
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "AGENT_NOT_READY", "message": f"Agent is '{agent['status']}', must be 'ready' to run", "details": {}}},
        )

    run = await run_repo.create(agent_id=agent_id, inputs=body.inputs)
    # Trigger execution in the background
    background_tasks.add_task(execution_service.run_standalone_agent, run["id"])
    return {"run_id": run["id"], "status": run["status"]}


@router.get("/{agent_id}/runs")
async def list_agent_runs(agent_id: str, request: Request):
    run_repo = request.app.state.run_repo
    return await run_repo.list_by_agent(agent_id)

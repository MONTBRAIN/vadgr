"""Agent CRUD routes."""

import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from api.models.agent import AgentCreate, AgentUpdate, AgentRunRequest

router = APIRouter(prefix="/api/agents", tags=["agents"])

# Resolve project root so forge_path cleanup works regardless of cwd
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _not_found(agent_id: str):
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "AGENT_NOT_FOUND", "message": f"Agent with id '{agent_id}' not found", "details": {}}},
    )


@router.post("", status_code=201)
async def create_agent(body: AgentCreate, request: Request, background_tasks: BackgroundTasks):
    agent_service = request.app.state.agent_service
    steps_dicts = [s.model_dump() if hasattr(s, "model_dump") else s for s in body.steps]
    input_schema_dicts = [s.model_dump(exclude_none=False) for s in body.input_schema]
    output_schema_dicts = [s.model_dump(exclude_none=False) for s in body.output_schema]
    agent = await agent_service.create_agent(
        name=body.name,
        description=body.description,
        steps=steps_dicts,
        samples=body.samples,
        input_schema=input_schema_dicts,
        output_schema=output_schema_dicts,
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
    if "steps" in fields:
        fields["steps"] = [s.model_dump() if hasattr(s, "model_dump") else s for s in body.steps]
    if "input_schema" in fields:
        fields["input_schema"] = [s.model_dump(exclude_none=False) for s in body.input_schema]
    if "output_schema" in fields:
        fields["output_schema"] = [s.model_dump(exclude_none=False) for s in body.output_schema]

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


@router.delete("", status_code=200)
async def delete_all_agents(request: Request):
    repo = request.app.state.agent_repo
    # Clean up all forge output folders before deleting
    agents = await repo.list_all()
    for agent in agents:
        forge_path = agent.get("forge_path", "")
        if forge_path:
            path = PROJECT_ROOT / forge_path
            if path.exists() and path.is_dir():
                shutil.rmtree(path)
    count = await repo.delete_all()
    return {"deleted": count}


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: str, request: Request):
    repo = request.app.state.agent_repo
    agent = await repo.get(agent_id)
    if not agent:
        return _not_found(agent_id)
    # Clean up the output folder if it exists
    forge_path = agent.get("forge_path", "")
    if forge_path:
        path = PROJECT_ROOT / forge_path
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

    run_provider = body.provider or agent["provider"]
    run_model = body.model or agent["model"]

    run = await run_repo.create(
        agent_id=agent_id,
        inputs=body.inputs,
        provider=run_provider,
        model=run_model,
    )
    # Trigger execution in the background
    background_tasks.add_task(execution_service.run_standalone_agent, run["id"])
    return {"run_id": run["id"], "status": run["status"]}


@router.get("/{agent_id}/runs")
async def list_agent_runs(agent_id: str, request: Request):
    run_repo = request.app.state.run_repo
    return await run_repo.list_by_agent(agent_id)

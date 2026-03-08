"""Agent CRUD routes."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.models.agent import AgentCreate, AgentUpdate, AgentRunRequest

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _not_found(agent_id: str):
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "AGENT_NOT_FOUND", "message": f"Agent with id '{agent_id}' not found", "details": {}}},
    )


@router.post("", status_code=201)
async def create_agent(body: AgentCreate, request: Request):
    repo = request.app.state.agent_repo
    agent = await repo.create(
        name=body.name,
        description=body.description,
        samples=body.samples,
        computer_use=body.computer_use,
        provider=body.provider,
        model=body.model,
    )
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


@router.put("/{agent_id}")
async def update_agent(agent_id: str, body: AgentUpdate, request: Request):
    repo = request.app.state.agent_repo
    fields = body.model_dump(exclude_none=True)
    if "input_schema" in fields:
        fields["input_schema"] = [s.model_dump() if hasattr(s, "model_dump") else s for s in fields["input_schema"]]
    if "output_schema" in fields:
        fields["output_schema"] = [s.model_dump() if hasattr(s, "model_dump") else s for s in fields["output_schema"]]
    agent = await repo.update(agent_id, **fields)
    if not agent:
        return _not_found(agent_id)
    return agent


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: str, request: Request):
    repo = request.app.state.agent_repo
    deleted = await repo.delete(agent_id)
    if not deleted:
        return _not_found(agent_id)


@router.post("/{agent_id}/run", status_code=202)
async def run_agent(agent_id: str, body: AgentRunRequest, request: Request):
    agent_repo = request.app.state.agent_repo
    run_repo = request.app.state.run_repo
    agent = await agent_repo.get(agent_id)
    if not agent:
        return _not_found(agent_id)
    run = await run_repo.create(agent_id=agent_id, inputs=body.inputs)
    return {"run_id": run["id"], "status": run["status"]}


@router.get("/{agent_id}/runs")
async def list_agent_runs(agent_id: str, request: Request):
    run_repo = request.app.state.run_repo
    return await run_repo.list_by_agent(agent_id)

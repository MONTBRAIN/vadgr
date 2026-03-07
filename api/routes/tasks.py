"""Task CRUD routes."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.models.task import TaskCreate, TaskUpdate, TaskRunRequest

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _not_found(task_id: str):
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "TASK_NOT_FOUND", "message": f"Task with id '{task_id}' not found", "details": {}}},
    )


@router.post("", status_code=201)
async def create_task(body: TaskCreate, request: Request):
    repo = request.app.state.task_repo
    task = await repo.create(
        name=body.name,
        description=body.description,
        type=body.type.value,
        samples=body.samples,
        computer_use=body.computer_use,
        provider=body.provider,
        model=body.model,
    )
    return task


@router.get("")
async def list_tasks(request: Request):
    repo = request.app.state.task_repo
    return await repo.list_all()


@router.get("/{task_id}")
async def get_task(task_id: str, request: Request):
    repo = request.app.state.task_repo
    task = await repo.get(task_id)
    if not task:
        return _not_found(task_id)
    return task


@router.put("/{task_id}")
async def update_task(task_id: str, body: TaskUpdate, request: Request):
    repo = request.app.state.task_repo
    fields = body.model_dump(exclude_none=True)
    if "input_schema" in fields:
        fields["input_schema"] = [s.model_dump() if hasattr(s, "model_dump") else s for s in fields["input_schema"]]
    if "output_schema" in fields:
        fields["output_schema"] = [s.model_dump() if hasattr(s, "model_dump") else s for s in fields["output_schema"]]
    task = await repo.update(task_id, **fields)
    if not task:
        return _not_found(task_id)
    return task


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: str, request: Request):
    repo = request.app.state.task_repo
    deleted = await repo.delete(task_id)
    if not deleted:
        return _not_found(task_id)


@router.post("/{task_id}/run", status_code=202)
async def run_task(task_id: str, body: TaskRunRequest, request: Request):
    task_repo = request.app.state.task_repo
    run_repo = request.app.state.run_repo
    task = await task_repo.get(task_id)
    if not task:
        return _not_found(task_id)
    run = await run_repo.create(task_id=task_id, inputs=body.inputs)
    return {"run_id": run["id"], "status": run["status"]}


@router.get("/{task_id}/runs")
async def list_task_runs(task_id: str, request: Request):
    run_repo = request.app.state.run_repo
    return await run_repo.list_by_task(task_id)

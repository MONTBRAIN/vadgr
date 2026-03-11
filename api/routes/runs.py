"""Run lifecycle routes."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.models.run import RunCreate

router = APIRouter(tags=["runs"])


def _not_found(run_id: str):
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "RUN_NOT_FOUND", "message": f"Run with id '{run_id}' not found", "details": {}}},
    )


@router.post("/api/projects/{project_id}/runs", status_code=202)
async def start_project_run(project_id: str, body: RunCreate, request: Request):
    project_repo = request.app.state.project_repo
    run_repo = request.app.state.run_repo
    project = await project_repo.get(project_id)
    if not project:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "PROJECT_NOT_FOUND", "message": f"Project with id '{project_id}' not found", "details": {}}},
        )
    run = await run_repo.create(project_id=project_id, inputs=body.inputs)
    return {"run_id": run["id"], "status": run["status"]}


@router.delete("/api/runs", status_code=200)
async def delete_all_runs(request: Request):
    run_repo = request.app.state.run_repo
    count = await run_repo.delete_all()
    return {"deleted": count}


@router.get("/api/runs")
async def list_runs(request: Request, status: str | None = None):
    run_repo = request.app.state.run_repo
    return await run_repo.list_all(status=status)


@router.get("/api/runs/{run_id}")
async def get_run(run_id: str, request: Request):
    run_repo = request.app.state.run_repo
    run = await run_repo.get(run_id)
    if not run:
        return _not_found(run_id)
    return run


@router.post("/api/runs/{run_id}/cancel")
async def cancel_run(run_id: str, request: Request):
    run_repo = request.app.state.run_repo
    run = await run_repo.get(run_id)
    if not run:
        return _not_found(run_id)
    if run["status"] in ("completed", "failed"):
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "RUN_NOT_ACTIVE", "message": "Run is already finished", "details": {}}},
        )
    updated = await run_repo.update_status(run_id, "failed")
    return updated


@router.post("/api/runs/{run_id}/approve")
async def approve_run(run_id: str, request: Request):
    run_repo = request.app.state.run_repo
    run = await run_repo.get(run_id)
    if not run:
        return _not_found(run_id)
    if run["status"] != "awaiting_approval":
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "NO_GATE_PENDING", "message": "No approval gate is pending", "details": {}}},
        )
    updated = await run_repo.update_status(run_id, "running")
    return updated

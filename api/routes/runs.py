"""Run lifecycle routes."""

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.models.run import RunCreate

router = APIRouter(tags=["runs"])


def _not_found(run_id: str):
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "RUN_NOT_FOUND", "message": f"Run with id '{run_id}' not found", "details": {}}},
    )


@router.post("/api/runs", status_code=202)
async def start_run(body: RunCreate, request: Request):
    """Start a run from a task sentence.

    `202` and not `201`: the row exists but nothing has run yet. The sentence
    rides twice on purpose, as the run's title and as its work, because the
    display fact and the thing handed to the loop are different jobs that happen
    to share a string today.
    """
    run_repo = request.app.state.run_repo
    execution_service = request.app.state.execution_service
    run = await run_repo.create(
        title=body.task,
        inputs={"task": body.task},
        provider=body.provider,
        model=body.model,
    )
    task = asyncio.create_task(execution_service.start_run(run["id"]))
    # Registered before the response returns, because this dict is what
    # POST /api/runs/{id}/cancel reaches for. A trigger that skipped it would
    # ship a cancel that answers 200 and cancels nothing.
    request.app.state.active_run_tasks[run["id"]] = task
    task.add_done_callback(
        lambda _: request.app.state.active_run_tasks.pop(run["id"], None)
    )
    return run


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
    # Signal the asyncio task - CancelledError propagates into execute_streaming
    # which kills the subprocess (and its full process group) in the finally block
    task = request.app.state.active_run_tasks.get(run_id)
    if task and not task.done():
        task.cancel()
    updated = await run_repo.update_status(run_id, "failed")
    return updated


@router.post("/api/runs/{run_id}/resume")
async def resume_run(run_id: str, request: Request):
    run_repo = request.app.state.run_repo
    run = await run_repo.get(run_id)
    if not run:
        return _not_found(run_id)
    # Idempotent: if already running (e.g. button spammed), return current state
    if run["status"] == "running":
        return {"run_id": run_id, "status": "running", "message": "Already running"}
    if run["status"] not in ("failed",):
        return JSONResponse(
            status_code=409,
            content={"error": {
                "code": "RUN_NOT_RESUMABLE",
                "message": f"Only failed runs can be resumed (current status: {run['status']})",
                "details": {},
            }},
        )
    # Prevent duplicate tasks if there's already an active one for this run
    existing_task = request.app.state.active_run_tasks.get(run_id)
    if existing_task and not existing_task.done():
        return {"run_id": run_id, "status": "running", "message": "Already resuming"}

    execution_service = request.app.state.execution_service
    task = asyncio.create_task(execution_service.resume_run(run_id))
    request.app.state.active_run_tasks[run_id] = task
    task.add_done_callback(
        lambda _: request.app.state.active_run_tasks.pop(run_id, None)
    )
    return {"run_id": run_id, "status": "running", "message": "Resuming"}

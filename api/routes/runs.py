"""Run lifecycle routes."""

import json
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from api.models.run import RunCreate

# Project root for resolving output file paths
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

router = APIRouter(tags=["runs"])


def _not_found(run_id: str):
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "RUN_NOT_FOUND", "message": f"Run with id '{run_id}' not found", "details": {}}},
    )


def _resolve_output_path(forge_path: str, value: str) -> Path | None:
    candidates = []
    if forge_path:
        candidates.append(_PROJECT_ROOT / forge_path / value)
    candidates.append(_PROJECT_ROOT / value)

    for path in candidates:
        resolved = path.resolve()
        if _PROJECT_ROOT.resolve() in resolved.parents and resolved.is_file():
            return resolved
    return None


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
    # Signal the asyncio task - CancelledError propagates into execute_streaming
    # which kills the subprocess (and its full process group) in the finally block
    task = request.app.state.active_run_tasks.get(run_id)
    if task and not task.done():
        task.cancel()
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


@router.get("/api/runs/{run_id}/outputs/{field_name}")
async def get_run_output(run_id: str, field_name: str, request: Request):
    """Return the content of a run output field.

    If the output value is a file path on disk, reads and returns the file content.
    Otherwise returns the raw value as text.
    """
    run_repo = request.app.state.run_repo
    agent_repo = request.app.state.agent_repo
    run = await run_repo.get(run_id)
    if not run:
        return _not_found(run_id)

    outputs = run.get("outputs") or {}
    if field_name not in outputs:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "OUTPUT_NOT_FOUND", "message": f"Output '{field_name}' not found in run", "details": {}}},
        )

    value = outputs[field_name]
    agent = await agent_repo.get(run.get("agent_id", "")) if run.get("agent_id") else None
    forge_path = agent.get("forge_path", "") if agent else ""

    if isinstance(value, dict) and value.get("kind") in {"file", "archive", "directory"}:
        resolved = _resolve_output_path(forge_path, value.get("path", ""))
        if resolved:
            return FileResponse(
                path=resolved,
                media_type=value.get("mime_type") or "application/octet-stream",
                filename=value.get("filename") or resolved.name,
            )
        return PlainTextResponse(str(value))

    if not isinstance(value, str):
        return PlainTextResponse(str(value))

    resolved = _resolve_output_path(forge_path, value)
    if resolved:
        mime_type, _ = mimetypes.guess_type(resolved.name)
        return FileResponse(
            path=resolved,
            media_type=mime_type or "text/plain",
            filename=resolved.name,
        )

    return PlainTextResponse(value)


def _read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file and return list of parsed events."""
    if not path.exists():
        return []
    events = []
    for line in path.read_text().splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


@router.get("/api/runs/{run_id}/logs")
async def get_run_logs(run_id: str, request: Request):
    """Return all log events for a run (execution + all steps, sorted by timestamp)."""
    run_repo = request.app.state.run_repo
    run = await run_repo.get(run_id)
    if not run:
        return _not_found(run_id)

    log_path = run.get("log_path")
    if not log_path:
        return JSONResponse(content=[])

    log_dir = _PROJECT_ROOT / log_path
    if not log_dir.exists():
        return JSONResponse(content=[])

    # Read execution.jsonl + all step files, merge and sort by timestamp
    all_events = _read_jsonl(log_dir / "execution.jsonl")
    for step_file in sorted(log_dir.iterdir()):
        if step_file.name.startswith("step_") and step_file.name.endswith(".jsonl"):
            all_events.extend(_read_jsonl(step_file))

    all_events.sort(key=lambda e: e.get("timestamp", ""))
    return JSONResponse(content=all_events)


@router.get("/api/runs/{run_id}/logs/{step_file}")
async def get_step_log(run_id: str, step_file: str, request: Request):
    """Return per-step log events for a run."""
    run_repo = request.app.state.run_repo
    run = await run_repo.get(run_id)
    if not run:
        return _not_found(run_id)

    log_path = run.get("log_path")
    if not log_path:
        return JSONResponse(content=[])

    # Security: only allow step_*.jsonl filenames
    if not step_file.startswith("step_") or not step_file.endswith(".jsonl"):
        return JSONResponse(content=[])

    log_dir = _PROJECT_ROOT / log_path
    step_path = log_dir / step_file
    resolved = step_path.resolve()
    if _PROJECT_ROOT.resolve() not in resolved.parents:
        return JSONResponse(content=[])

    return JSONResponse(content=_read_jsonl(step_path))

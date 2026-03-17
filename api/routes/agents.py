"""Agent CRUD routes."""

import io
import json
import subprocess
import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from api.models.agent import AgentCreate, AgentUpdate, AgentRunRequest

router = APIRouter(prefix="/api/agents", tags=["agents"])

# Resolve project root so forge_path cleanup works regardless of cwd
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _not_found(agent_id: str):
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "AGENT_NOT_FOUND", "message": f"Agent with id '{agent_id}' not found", "details": {}}},
    )


def _build_export_manifest(agent: dict) -> dict:
    return {
        "export_version": 2,
        "name": agent["name"],
        "description": agent.get("description", ""),
        "steps": agent.get("steps", []),
        "samples": agent.get("samples", []),
        "input_schema": agent.get("input_schema", []),
        "output_schema": agent.get("output_schema", []),
        "computer_use": agent.get("computer_use", False),
        "provider": agent.get("provider"),
        "model": agent.get("model"),
    }


def _safe_extract_zip(archive: zipfile.ZipFile, target_dir: Path) -> None:
    target_root = target_dir.resolve()
    for member in archive.infolist():
        member_path = target_dir / member.filename
        resolved = member_path.resolve()
        if target_root not in resolved.parents and resolved != target_root:
            raise ValueError(f"Unsafe archive entry: {member.filename}")
        archive.extract(member, target_dir)


def _set_repo_identity(agent_root: Path) -> None:
    subprocess.run(
        ["git", "-C", str(agent_root), "config", "user.name", "Agent Forge"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(agent_root), "config", "user.email", "agent-forge@local"],
        check=True,
        capture_output=True,
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
        if current["status"] in ("creating", "updating", "importing"):
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
    artifact_service = request.app.state.artifact_service

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
    materialized_inputs = artifact_service.materialize_run_inputs(
        forge_path=agent.get("forge_path", ""),
        run_id=run["id"],
        inputs=body.inputs,
    )
    if materialized_inputs != body.inputs:
        await run_repo.set_inputs(run["id"], materialized_inputs)
    # Trigger execution in the background
    background_tasks.add_task(execution_service.run_standalone_agent, run["id"])
    return {"run_id": run["id"], "status": run["status"]}


@router.get("/{agent_id}/runs")
async def list_agent_runs(agent_id: str, request: Request):
    run_repo = request.app.state.run_repo
    return await run_repo.list_by_agent(agent_id)


@router.post("/{agent_id}/uploads", status_code=201)
async def upload_agent_artifact(
    agent_id: str,
    request: Request,
    field_name: str = Form(...),
    file: UploadFile = File(...),
):
    repo = request.app.state.agent_repo
    artifact_service = request.app.state.artifact_service

    agent = await repo.get(agent_id)
    if not agent:
        return _not_found(agent_id)
    if agent["status"] != "ready":
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "AGENT_NOT_READY", "message": f"Agent is '{agent['status']}', must be 'ready' to upload artifacts", "details": {}}},
        )

    schema_field = next(
        (field for field in (agent.get("input_schema") or []) if field.get("name") == field_name),
        None,
    )
    if schema_field is None:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "INVALID_INPUT_FIELD", "message": f"Unknown input field '{field_name}'", "details": {}}},
        )
    if schema_field.get("type") not in {"file", "archive", "directory"}:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "INVALID_INPUT_FIELD", "message": f"Input field '{field_name}' does not accept uploaded artifacts", "details": {}}},
        )

    content = await file.read()
    validation_error = artifact_service.validate_upload(
        schema_field=schema_field,
        filename=file.filename or "upload.bin",
        content_type=file.content_type,
        size_bytes=len(content),
    )
    if validation_error:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "INVALID_ARTIFACT_UPLOAD", "message": validation_error, "details": {"field_name": field_name}}},
        )

    descriptor = artifact_service.stage_upload(
        forge_path=agent.get("forge_path", ""),
        filename=file.filename or "upload.bin",
        content=content,
    )
    return descriptor


@router.get("/{agent_id}/export")
async def export_agent(agent_id: str, request: Request):
    repo = request.app.state.agent_repo
    agent = await repo.get(agent_id)
    if not agent:
        return _not_found(agent_id)

    forge_path = agent.get("forge_path", "")
    agent_root = (PROJECT_ROOT / forge_path).resolve()
    if not forge_path or not agent_root.is_dir():
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "AGENT_NOT_EXPORTED", "message": "Agent folder does not exist on disk", "details": {}}},
        )

    with tempfile.TemporaryDirectory() as temp_dir:
        bundle_path = Path(temp_dir) / "agent.bundle"
        subprocess.run(
            ["git", "-C", str(agent_root), "bundle", "create", str(bundle_path), "--all"],
            check=True,
            capture_output=True,
        )
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("agent-forge.json", json.dumps(_build_export_manifest(agent), indent=2))
            archive.write(bundle_path, arcname="agent.bundle")
    payload.seek(0)
    filename = f"{agent['name'].replace(' ', '-').lower() or agent_id}.zip"
    return StreamingResponse(
        payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import", status_code=201)
async def import_agent(request: Request, file: UploadFile = File(...)):
    repo = request.app.state.agent_repo

    archive_bytes = await file.read()
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "INVALID_AGENT_ARCHIVE", "message": "Archive must be a valid zip file", "details": {}}},
        )

    with archive:
        try:
            manifest = json.loads(archive.read("agent-forge.json"))
        except KeyError:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_AGENT_ARCHIVE", "message": "Archive is missing agent-forge.json", "details": {}}},
            )
        try:
            archive.getinfo("agent.bundle")
        except KeyError:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_AGENT_ARCHIVE", "message": "Archive is missing agent.bundle", "details": {}}},
            )

        agent = await repo.create(
            name=manifest.get("name") or "Imported Agent",
            description=manifest.get("description", ""),
            status="importing",
            steps=manifest.get("steps", []),
            samples=manifest.get("samples", []),
            input_schema=manifest.get("input_schema", []),
            output_schema=manifest.get("output_schema", []),
            computer_use=manifest.get("computer_use", False),
            provider=manifest.get("provider", "claude_code"),
            model=manifest.get("model", "claude-sonnet-4-6"),
        )
        forge_path = f"output/{agent['id']}"
        target_dir = PROJECT_ROOT / forge_path
        try:
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                _safe_extract_zip(archive, temp_path)
                bundle_path = temp_path / "agent.bundle"
                subprocess.run(
                    ["git", "clone", str(bundle_path), str(target_dir)],
                    check=True,
                    capture_output=True,
                )
            _set_repo_identity(target_dir)
            agent_service = request.app.state.agent_service
            agent_service.ensure_agent_runtime_scaffold(forge_path)
            agent_service.ensure_agent_script_environment(forge_path)
            await repo.update(agent["id"], forge_path=forge_path, status="ready")
            return await repo.get(agent["id"])
        except Exception:
            if target_dir.exists():
                shutil.rmtree(target_dir)
            await repo.delete(agent["id"])
            raise

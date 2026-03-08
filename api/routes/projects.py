"""Project CRUD and canvas routes."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.models.project import (
    ProjectCreate, ProjectUpdate, NodeCreate, NodeUpdate, EdgeCreate,
)
from api.engine.dag import DAG

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _not_found(project_id: str):
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "PROJECT_NOT_FOUND", "message": f"Project with id '{project_id}' not found", "details": {}}},
    )


@router.post("", status_code=201)
async def create_project(body: ProjectCreate, request: Request):
    repo = request.app.state.project_repo
    return await repo.create(name=body.name, description=body.description)


@router.get("")
async def list_projects(request: Request):
    repo = request.app.state.project_repo
    return await repo.list_all()


@router.get("/{project_id}")
async def get_project(project_id: str, request: Request):
    repo = request.app.state.project_repo
    project = await repo.get(project_id)
    if not project:
        return _not_found(project_id)
    nodes = await repo.get_nodes(project_id)
    edges = await repo.get_edges(project_id)
    return {**project, "nodes": nodes, "edges": edges}


@router.put("/{project_id}")
async def update_project(project_id: str, body: ProjectUpdate, request: Request):
    repo = request.app.state.project_repo
    fields = body.model_dump(exclude_none=True)
    project = await repo.update(project_id, **fields)
    if not project:
        return _not_found(project_id)
    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, request: Request):
    repo = request.app.state.project_repo
    deleted = await repo.delete(project_id)
    if not deleted:
        return _not_found(project_id)


@router.post("/{project_id}/nodes", status_code=201)
async def add_node(project_id: str, body: NodeCreate, request: Request):
    repo = request.app.state.project_repo
    project = await repo.get(project_id)
    if not project:
        return _not_found(project_id)
    return await repo.add_node(
        project_id=project_id,
        agent_id=body.agent_id,
        config=body.config,
        position_x=body.position_x,
        position_y=body.position_y,
    )


@router.put("/{project_id}/nodes/{node_id}")
async def update_node(project_id: str, node_id: str, body: NodeUpdate, request: Request):
    repo = request.app.state.project_repo
    fields = body.model_dump(exclude_none=True)
    node = await repo.update_node(node_id, **fields)
    if not node:
        return JSONResponse(status_code=404, content={"error": {"code": "NODE_NOT_FOUND", "message": f"Node '{node_id}' not found", "details": {}}})
    return node


@router.delete("/{project_id}/nodes/{node_id}", status_code=204)
async def delete_node(project_id: str, node_id: str, request: Request):
    repo = request.app.state.project_repo
    deleted = await repo.delete_node(node_id)
    if not deleted:
        return JSONResponse(status_code=404, content={"error": {"code": "NODE_NOT_FOUND", "message": f"Node '{node_id}' not found", "details": {}}})


@router.post("/{project_id}/edges", status_code=201)
async def add_edge(project_id: str, body: EdgeCreate, request: Request):
    repo = request.app.state.project_repo
    project = await repo.get(project_id)
    if not project:
        return _not_found(project_id)
    return await repo.add_edge(
        project_id=project_id,
        source_node_id=body.source_node_id,
        target_node_id=body.target_node_id,
        source_output=body.source_output,
        target_input=body.target_input,
    )


@router.delete("/{project_id}/edges/{edge_id}", status_code=204)
async def delete_edge(project_id: str, edge_id: str, request: Request):
    repo = request.app.state.project_repo
    deleted = await repo.delete_edge(edge_id)
    if not deleted:
        return JSONResponse(status_code=404, content={"error": {"code": "EDGE_NOT_FOUND", "message": f"Edge '{edge_id}' not found", "details": {}}})


@router.post("/{project_id}/validate")
async def validate_project(project_id: str, request: Request):
    repo = request.app.state.project_repo
    project = await repo.get(project_id)
    if not project:
        return _not_found(project_id)
    nodes = await repo.get_nodes(project_id)
    edges = await repo.get_edges(project_id)
    dag = DAG(nodes=nodes, edges=edges)
    errors = dag.validate()
    return {"valid": len(errors) == 0, "errors": errors}

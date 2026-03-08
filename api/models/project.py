"""Project, node, and edge Pydantic models."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None


class NodeCreate(BaseModel):
    agent_id: str
    config: dict[str, Any] = {}
    position_x: float = 0.0
    position_y: float = 0.0


class NodeUpdate(BaseModel):
    config: Optional[dict[str, Any]] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None


class EdgeCreate(BaseModel):
    source_node_id: str
    target_node_id: str
    source_output: str
    target_input: str


class ProjectNode(BaseModel):
    id: str
    project_id: str
    agent_id: str
    config: dict[str, Any] = {}
    position_x: float = 0.0
    position_y: float = 0.0


class ProjectEdge(BaseModel):
    id: str
    project_id: str
    source_node_id: str
    target_node_id: str
    source_output: str
    target_input: str


class Project(BaseModel):
    id: str
    name: str
    description: str = ""
    nodes: list[ProjectNode] = []
    edges: list[ProjectEdge] = []
    created_at: datetime
    updated_at: datetime


class ValidationError(BaseModel):
    type: str
    message: str
    node_id: Optional[str] = None


class ValidateResponse(BaseModel):
    valid: bool
    errors: list[ValidationError] = []


class CanvasSave(BaseModel):
    nodes: list[NodeCreate] = []
    edges: list[EdgeCreate] = []

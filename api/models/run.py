"""Run and agent run Pydantic models."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from .common import RunStatus, AgentRunStatus


class RunCreate(BaseModel):
    inputs: dict[str, Any] = {}


class Run(BaseModel):
    id: str
    project_id: Optional[str] = None
    agent_id: Optional[str] = None
    status: RunStatus = RunStatus.QUEUED
    inputs: dict[str, Any] = {}
    outputs: dict[str, Any] = {}
    provider: Optional[str] = None
    model: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class AgentRun(BaseModel):
    id: str
    run_id: str
    node_id: str
    status: AgentRunStatus = AgentRunStatus.PENDING
    inputs: dict[str, Any] = {}
    outputs: dict[str, Any] = {}
    logs: str = ""
    duration_ms: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class RunStartResponse(BaseModel):
    run_id: str
    status: RunStatus

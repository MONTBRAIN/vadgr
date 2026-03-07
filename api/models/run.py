"""Run and task run Pydantic models."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from .common import RunStatus, TaskRunStatus


class RunCreate(BaseModel):
    inputs: dict[str, Any] = {}


class Run(BaseModel):
    id: str
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    status: RunStatus = RunStatus.QUEUED
    inputs: dict[str, Any] = {}
    outputs: dict[str, Any] = {}
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class TaskRun(BaseModel):
    id: str
    run_id: str
    node_id: str
    status: TaskRunStatus = TaskRunStatus.PENDING
    inputs: dict[str, Any] = {}
    outputs: dict[str, Any] = {}
    logs: str = ""
    duration_ms: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class RunStartResponse(BaseModel):
    run_id: str
    status: RunStatus

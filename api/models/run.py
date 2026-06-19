"""Run and agent run Pydantic models."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel

from .common import RunStatus, AgentRunStatus, StrictBody


class RunEventType(str, Enum):
    STARTED = "started"
    TOOL_CALL = "tool_call"
    OUTPUT = "output"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class RunEvent(BaseModel):
    """The WS stream payload. Transient -- derived from run/agent-run state,
    never persisted as a table."""

    type: RunEventType
    timestamp: datetime
    payload: dict = {}


class RunCreate(StrictBody):
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

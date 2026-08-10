"""Run Pydantic models."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, model_validator

from .common import RunStatus, StrictBody


class RunEventType(str, Enum):
    STARTED = "started"
    TOOL_CALL = "tool_call"
    OUTPUT = "output"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class RunEvent(BaseModel):
    """The WS stream payload. Transient -- derived from run state, never
    persisted as a table."""

    type: RunEventType
    timestamp: datetime
    payload: dict = {}


class RunCreate(StrictBody):
    task: str
    provider: Optional[str] = None
    model: Optional[str] = None

    @model_validator(mode="after")
    def validate_task_present(self):
        if not self.task.strip():
            raise ValueError("task must not be empty")
        return self

    @model_validator(mode="after")
    def validate_provider_model_pair(self):
        # One of the pair without the other is a 422, never a half-resolved run:
        # a model named against whatever provider happened to be the machine's
        # default is a run nobody asked for.
        if (self.provider is None) != (self.model is None):
            raise ValueError("provider and model must be provided together")
        return self


class Run(BaseModel):
    id: str
    title: str = ""
    status: RunStatus = RunStatus.QUEUED
    inputs: dict[str, Any] = {}
    outputs: dict[str, Any] = {}
    provider: Optional[str] = None
    model: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

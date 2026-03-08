"""Shared enums, pagination, and error models."""

from enum import Enum

from pydantic import BaseModel


class AgentType(str, Enum):
    AGENT = "agent"
    APPROVAL = "approval"
    INPUT = "input"
    OUTPUT = "output"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict = {}


class ErrorEnvelope(BaseModel):
    error: ErrorResponse

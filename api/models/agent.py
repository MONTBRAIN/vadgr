"""Agent Pydantic models."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from .common import AgentType


class SchemaField(BaseModel):
    name: str
    type: str = "text"
    required: bool = True


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    steps: list[str] = []
    samples: list[str] = []
    computer_use: bool = False
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-6"


class AgentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=10000)
    status: Optional[str] = None
    steps: Optional[list[str]] = None
    samples: Optional[list[str]] = None
    input_schema: Optional[list[SchemaField]] = None
    output_schema: Optional[list[SchemaField]] = None
    computer_use: Optional[bool] = None
    provider: Optional[str] = None
    model: Optional[str] = None


class Agent(BaseModel):
    id: str
    name: str
    description: str
    type: AgentType
    status: str = "creating"
    forge_path: str = ""
    steps: list[str] = []
    samples: list[str] = []
    input_schema: list[SchemaField] = []
    output_schema: list[SchemaField] = []
    computer_use: bool = False
    forge_config: dict[str, Any] = {}
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-6"
    created_at: datetime
    updated_at: datetime


class AgentRunRequest(BaseModel):
    inputs: dict[str, Any] = {}

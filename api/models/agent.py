"""Agent Pydantic models."""

from datetime import datetime
from typing import Any, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from .common import AgentType


class SchemaField(BaseModel):
    name: str
    type: str = "text"
    required: bool = True
    label: Optional[str] = None
    description: Optional[str] = None
    placeholder: Optional[str] = None
    options: Optional[list[str]] = None


class StepDefinition(BaseModel):
    name: str
    computer_use: bool = False


def _normalize_steps(steps: list) -> list[StepDefinition]:
    """Convert a list of strings or dicts to StepDefinition objects."""
    result = []
    for s in steps:
        if isinstance(s, str):
            result.append(StepDefinition(name=s, computer_use=False))
        elif isinstance(s, dict):
            result.append(StepDefinition(**s))
        elif isinstance(s, StepDefinition):
            result.append(s)
        else:
            result.append(StepDefinition(name=str(s), computer_use=False))
    return result


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    steps: list[Union[str, StepDefinition]] = []
    samples: list[str] = []
    input_schema: list[SchemaField] = []
    output_schema: list[SchemaField] = []
    computer_use: bool = False
    provider: str = "claude_code"
    model: str = "claude-sonnet-4-6"

    @field_validator("steps", mode="before")
    @classmethod
    def normalize_steps(cls, v):
        return _normalize_steps(v) if v else []

    def model_post_init(self, __context: Any) -> None:
        """Derive computer_use from steps if any step has computer_use=True."""
        if self.steps and any(
            s.computer_use for s in self.steps if isinstance(s, StepDefinition)
        ):
            object.__setattr__(self, "computer_use", True)


class AgentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=10000)
    status: Optional[str] = None
    steps: Optional[list[Union[str, StepDefinition]]] = None
    samples: Optional[list[str]] = None
    input_schema: Optional[list[SchemaField]] = None
    output_schema: Optional[list[SchemaField]] = None
    computer_use: Optional[bool] = None
    provider: Optional[str] = None
    model: Optional[str] = None

    @field_validator("steps", mode="before")
    @classmethod
    def normalize_steps(cls, v):
        return _normalize_steps(v) if v else v


class Agent(BaseModel):
    id: str
    name: str
    description: str
    type: AgentType
    status: str = "creating"
    forge_path: str = ""
    steps: list[StepDefinition] = []
    samples: list[str] = []
    input_schema: list[SchemaField] = []
    output_schema: list[SchemaField] = []
    computer_use: bool = False
    forge_config: dict[str, Any] = {}
    provider: str = "claude_code"
    model: str = "claude-sonnet-4-6"
    created_at: datetime
    updated_at: datetime

    @field_validator("steps", mode="before")
    @classmethod
    def normalize_steps(cls, v):
        return _normalize_steps(v) if v else []


class AgentRunRequest(BaseModel):
    inputs: dict[str, Any] = {}
    provider: Optional[str] = None
    model: Optional[str] = None

    @model_validator(mode="after")
    def validate_provider_model_pair(self):
        if (self.provider is None) != (self.model is None):
            raise ValueError("provider and model must be provided together")
        return self

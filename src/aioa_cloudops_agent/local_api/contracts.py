"""Strict local-only HTTP contracts for the Local-2 operator surface."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aioa_cloudops_agent.nz import (
    Checkpoint,
    CloudResourceType,
    FailureKind,
    ResourceQuery,
    Run,
    ShortIdentifier,
)

LOCAL_API_BODY_MAX_BYTES = 16_384
LOCAL_API_TOKEN_MIN_LENGTH = 32
LOCAL_API_TOKEN_MAX_LENGTH = 256


class LocalApiErrorCode(StrEnum):
    """Stable redacted HTTP errors; exception text never crosses the boundary."""

    BAD_REQUEST = "BAD_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    UNAUTHORIZED = "UNAUTHORIZED"
    POLICY_DENIED = "POLICY_DENIED"
    CONFLICT = "CONFLICT"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    WORKFLOW_FAILED = "WORKFLOW_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class LocalApiErrorResponse(BaseModel):
    """Public failure without provider payloads, secrets, or tracebacks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[False] = False
    error: LocalApiErrorCode
    failure_kind: FailureKind | None = None
    failure_code: str | None = Field(default=None, min_length=1, max_length=128)
    retryable: bool = False


class LocalStartRunRequest(BaseModel):
    """One exact inventory target; region and budgets remain server-owned."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    resource_type: CloudResourceType
    resource_id: ShortIdentifier

    @model_validator(mode="after")
    def validate_resource_identity(self) -> Self:
        ResourceQuery(
            resource_type=self.resource_type,
            resource_id=self.resource_id,
        )
        return self

    def to_query(self) -> ResourceQuery:
        return ResourceQuery(
            resource_type=self.resource_type,
            resource_id=self.resource_id,
        )


class LocalResumeRequest(BaseModel):
    """Require an explicit final execution gesture at the HTTP boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    confirm_execution: Literal[True]


class LocalRunView(BaseModel):
    """Authenticated durable state view; raw approval nonce is never persisted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run: Run
    checkpoint: Checkpoint | None = None

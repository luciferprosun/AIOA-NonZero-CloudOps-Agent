"""Typed contracts for one allow-listed sandbox EC2 inspection."""

import os
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final
from uuid import UUID

from aioa_cloudops_agent.config.settings import DEFAULT_AWS_REGION
from aioa_cloudops_agent.domain.aws_boundary import AwsOperationClass
from aioa_cloudops_agent.domain.enums import AuthorityGate
from aioa_cloudops_agent.domain.errors import ContractValidationError
from aioa_cloudops_agent.domain.identifiers import validate_correlation_id
from aioa_cloudops_agent.persistence.models import (
    compute_evidence_digest,
    validate_evidence_digest,
    validate_utc_timestamp,
)

DEFAULT_SANDBOX_TAG_KEY: Final = "AIOACloudOpsSandbox"
DEFAULT_SANDBOX_TAG_VALUE: Final = "true"
_INSTANCE_ID_PATTERN: Final = re.compile(r"^i-[0-9a-f]{8}(?:[0-9a-f]{9})?$")
_INSTANCE_TYPE_PATTERN: Final = re.compile(r"^[a-z0-9][a-z0-9.-]{1,63}$")
_AVAILABILITY_ZONE_PATTERN: Final = re.compile(r"^eu-central-1[a-z]$")


def validate_instance_id(value: object) -> str:
    """Return one syntactically valid EC2 instance identifier."""

    if not isinstance(value, str) or _INSTANCE_ID_PATTERN.fullmatch(value) is None:
        raise ContractValidationError("instance_id must be a valid EC2 instance identifier")
    return value


def _validate_non_empty_text(name: str, value: object, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise ContractValidationError(f"{name} must not contain surrounding whitespace")
    if len(value) > maximum:
        raise ContractValidationError(f"{name} must not exceed {maximum} characters")
    return value


class Ec2InstanceState(StrEnum):
    """States returned by EC2 DescribeInstances."""

    PENDING = "pending"
    RUNNING = "running"
    SHUTTING_DOWN = "shutting-down"
    TERMINATED = "terminated"
    STOPPING = "stopping"
    STOPPED = "stopped"


class Ec2MonitoringState(StrEnum):
    """Normalized detailed-monitoring state."""

    DISABLED = "disabled"
    DISABLING = "disabling"
    ENABLED = "enabled"
    PENDING = "pending"


@dataclass(frozen=True, slots=True)
class SandboxTarget:
    """Exact EC2 instance and tag proof required before inspection is accepted."""

    instance_id: str
    required_tag_key: str = DEFAULT_SANDBOX_TAG_KEY
    required_tag_value: str = DEFAULT_SANDBOX_TAG_VALUE

    def __post_init__(self) -> None:
        validate_instance_id(self.instance_id)
        _validate_non_empty_text("required_tag_key", self.required_tag_key, 128)
        _validate_non_empty_text("required_tag_value", self.required_tag_value, 256)

    @classmethod
    def from_environment(cls) -> "SandboxTarget":
        """Load the production target without inventing a sandbox identifier."""

        instance_id = os.getenv("SANDBOX_INSTANCE_ID")
        if instance_id is None:
            raise ContractValidationError("SANDBOX_INSTANCE_ID is required")
        return cls(
            instance_id=instance_id,
            required_tag_key=os.getenv("SANDBOX_TAG_KEY", DEFAULT_SANDBOX_TAG_KEY),
            required_tag_value=os.getenv("SANDBOX_TAG_VALUE", DEFAULT_SANDBOX_TAG_VALUE),
        )


@dataclass(frozen=True, slots=True)
class InstanceInspection:
    """Normalized, non-secret result for one proven sandbox instance."""

    correlation_id: UUID
    instance_id: str
    region: str
    state: Ec2InstanceState
    instance_type: str
    launch_time: datetime
    monitoring_state: Ec2MonitoringState
    availability_zone: str
    sandbox_tag_key: str
    sandbox_tag_value: str
    evidence_digest: str
    authority_gate: AuthorityGate = AuthorityGate.AUTO
    operation_class: AwsOperationClass = AwsOperationClass.READ_ONLY

    def __post_init__(self) -> None:
        if not isinstance(self.correlation_id, UUID):
            raise ContractValidationError("correlation_id must be a UUIDv7 value")
        validate_correlation_id(self.correlation_id)
        validate_instance_id(self.instance_id)
        if self.region != DEFAULT_AWS_REGION:
            raise ContractValidationError(f"inspection region must be {DEFAULT_AWS_REGION}")
        if not isinstance(self.state, Ec2InstanceState):
            raise ContractValidationError("state must be an Ec2InstanceState")
        if (
            not isinstance(self.instance_type, str)
            or _INSTANCE_TYPE_PATTERN.fullmatch(self.instance_type) is None
        ):
            raise ContractValidationError("instance_type is invalid")
        validate_utc_timestamp("launch_time", self.launch_time)
        if not isinstance(self.monitoring_state, Ec2MonitoringState):
            raise ContractValidationError("monitoring_state must be an Ec2MonitoringState")
        if (
            not isinstance(self.availability_zone, str)
            or _AVAILABILITY_ZONE_PATTERN.fullmatch(self.availability_zone) is None
        ):
            raise ContractValidationError("availability_zone must belong to the inspection region")
        _validate_non_empty_text("sandbox_tag_key", self.sandbox_tag_key, 128)
        _validate_non_empty_text("sandbox_tag_value", self.sandbox_tag_value, 256)
        if self.authority_gate is not AuthorityGate.AUTO:
            raise ContractValidationError("inspect_instance authority gate must be AUTO")
        if self.operation_class is not AwsOperationClass.READ_ONLY:
            raise ContractValidationError("inspect_instance operation must be READ_ONLY")
        validate_evidence_digest(self.evidence_digest)
        if self.evidence_digest != compute_evidence_digest(self.evidence_payload()):
            raise ContractValidationError("evidence_digest does not match inspection evidence")

    @classmethod
    def create(
        cls,
        *,
        correlation_id: UUID,
        instance_id: str,
        region: str,
        state: Ec2InstanceState,
        instance_type: str,
        launch_time: datetime,
        monitoring_state: Ec2MonitoringState,
        availability_zone: str,
        sandbox_tag_key: str,
        sandbox_tag_value: str,
    ) -> "InstanceInspection":
        """Build an inspection with a digest over canonical allow-listed evidence."""

        if not isinstance(correlation_id, UUID):
            raise ContractValidationError("correlation_id must be a UUIDv7 value")
        validate_correlation_id(correlation_id)
        validate_instance_id(instance_id)
        if region != DEFAULT_AWS_REGION:
            raise ContractValidationError(f"inspection region must be {DEFAULT_AWS_REGION}")
        if not isinstance(state, Ec2InstanceState):
            raise ContractValidationError("state must be an Ec2InstanceState")
        if (
            not isinstance(instance_type, str)
            or _INSTANCE_TYPE_PATTERN.fullmatch(instance_type) is None
        ):
            raise ContractValidationError("instance_type is invalid")
        validate_utc_timestamp("launch_time", launch_time)
        if not isinstance(monitoring_state, Ec2MonitoringState):
            raise ContractValidationError("monitoring_state must be an Ec2MonitoringState")
        if (
            not isinstance(availability_zone, str)
            or _AVAILABILITY_ZONE_PATTERN.fullmatch(availability_zone) is None
        ):
            raise ContractValidationError("availability_zone must belong to the inspection region")
        _validate_non_empty_text("sandbox_tag_key", sandbox_tag_key, 128)
        _validate_non_empty_text("sandbox_tag_value", sandbox_tag_value, 256)
        payload = {
            "authority_gate": AuthorityGate.AUTO.value,
            "availability_zone": availability_zone,
            "correlation_id": str(correlation_id),
            "instance_id": instance_id,
            "instance_type": instance_type,
            "launch_time": launch_time.isoformat(),
            "monitoring_state": monitoring_state.value,
            "operation_class": AwsOperationClass.READ_ONLY.value,
            "region": region,
            "sandbox_tag_key": sandbox_tag_key,
            "sandbox_tag_value": sandbox_tag_value,
            "state": state.value,
        }
        return cls(
            correlation_id=correlation_id,
            instance_id=instance_id,
            region=region,
            state=state,
            instance_type=instance_type,
            launch_time=launch_time,
            monitoring_state=monitoring_state,
            availability_zone=availability_zone,
            sandbox_tag_key=sandbox_tag_key,
            sandbox_tag_value=sandbox_tag_value,
            evidence_digest=compute_evidence_digest(payload),
        )

    def evidence_payload(self) -> dict[str, str]:
        """Return canonical evidence without raw provider metadata."""

        return {
            "authority_gate": self.authority_gate.value,
            "availability_zone": self.availability_zone,
            "correlation_id": str(self.correlation_id),
            "instance_id": self.instance_id,
            "instance_type": self.instance_type,
            "launch_time": self.launch_time.isoformat(),
            "monitoring_state": self.monitoring_state.value,
            "operation_class": self.operation_class.value,
            "region": self.region,
            "sandbox_tag_key": self.sandbox_tag_key,
            "sandbox_tag_value": self.sandbox_tag_value,
            "state": self.state.value,
        }

    def as_dict(self) -> dict[str, str]:
        """Return the typed public tool result as JSON-safe values."""

        return {**self.evidence_payload(), "evidence_digest": self.evidence_digest}

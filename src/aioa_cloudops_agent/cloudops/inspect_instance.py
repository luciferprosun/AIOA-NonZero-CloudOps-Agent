"""Fail-closed normalization for one configured sandbox EC2 instance."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from aioa_cloudops_agent.config.settings import DEFAULT_AWS_REGION
from aioa_cloudops_agent.domain.aws_boundary import (
    AwsOperation,
    AwsOperationClass,
    assess_aws_operation,
)
from aioa_cloudops_agent.domain.enums import AuthorityGate
from aioa_cloudops_agent.domain.errors import ContractValidationError, DomainError, ErrorCode
from aioa_cloudops_agent.domain.identifiers import validate_correlation_id
from aioa_cloudops_agent.persistence.models import (
    ProvenanceEventType,
    ProvenanceRecord,
)

from .ec2_readonly import Ec2DescribeInstancesClient
from .models import (
    Ec2InstanceState,
    Ec2MonitoringState,
    InstanceInspection,
    SandboxTarget,
    validate_instance_id,
)

INSPECT_INSTANCE_AWS_API: Final = "ec2:DescribeInstances"


class SandboxTargetMismatchError(DomainError):
    """Raised when the requested or returned instance is not the configured sandbox."""

    def __init__(self, message: str) -> None:
        super().__init__(
            code=ErrorCode.CLOUDOPS_INSPECTION_REJECTED,
            message=message,
            retryable=False,
        )


class InstanceInspectionError(DomainError):
    """Raised when provider evidence cannot be normalized unambiguously."""

    def __init__(self, message: str) -> None:
        super().__init__(
            code=ErrorCode.CLOUDOPS_RESPONSE_INVALID,
            message=message,
            retryable=False,
        )


def _required_mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InstanceInspectionError(f"DescribeInstances {name} is malformed")
    return value


def _required_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InstanceInspectionError(f"DescribeInstances {name} is missing or malformed")
    return value


def _single_returned_instance(response: Mapping[str, Any]) -> Mapping[str, Any]:
    reservations = response.get("Reservations")
    if not isinstance(reservations, list):
        raise InstanceInspectionError("DescribeInstances Reservations is missing or malformed")
    instances: list[Mapping[str, Any]] = []
    for reservation in reservations:
        reservation_mapping = _required_mapping(reservation, "reservation")
        reservation_instances = reservation_mapping.get("Instances")
        if not isinstance(reservation_instances, list):
            raise InstanceInspectionError("DescribeInstances Instances is missing or malformed")
        for instance in reservation_instances:
            instances.append(_required_mapping(instance, "instance"))
    if len(instances) != 1:
        raise InstanceInspectionError("DescribeInstances must return exactly one instance")
    return instances[0]


def _sandbox_tag(instance: Mapping[str, Any], target: SandboxTarget) -> tuple[str, str]:
    tags = instance.get("Tags")
    if not isinstance(tags, list):
        raise SandboxTargetMismatchError("Sandbox tag proof is missing")
    matches: list[str] = []
    for tag in tags:
        if not isinstance(tag, Mapping):
            raise InstanceInspectionError("DescribeInstances tag is malformed")
        if tag.get("Key") == target.required_tag_key and isinstance(tag.get("Value"), str):
            matches.append(tag["Value"])
    if matches != [target.required_tag_value]:
        raise SandboxTargetMismatchError("Required sandbox tag does not match")
    return target.required_tag_key, target.required_tag_value


class InspectInstanceService:
    """Inspect only one configured and tag-proven sandbox EC2 instance."""

    def __init__(
        self,
        client: Ec2DescribeInstancesClient,
        target: SandboxTarget,
        *,
        region: str = DEFAULT_AWS_REGION,
    ) -> None:
        if not isinstance(target, SandboxTarget):
            raise ContractValidationError("target must be a SandboxTarget")
        if region != DEFAULT_AWS_REGION:
            raise ContractValidationError(f"inspection region must be {DEFAULT_AWS_REGION}")
        self._client = client
        self._target = target
        self._region = region

    def inspect(self, *, instance_id: str, correlation_id: UUID) -> InstanceInspection:
        """Return normalized evidence after exact ID and sandbox-tag verification."""

        requested_id = validate_instance_id(instance_id)
        if not isinstance(correlation_id, UUID):
            raise ContractValidationError("correlation_id must be a UUIDv7 value")
        validate_correlation_id(correlation_id)
        if requested_id != self._target.instance_id:
            raise SandboxTargetMismatchError("Requested instance is not the configured sandbox")

        assessment = assess_aws_operation(AwsOperation.INSPECT_INSTANCE, AuthorityGate.AUTO)
        if assessment.operation_class is not AwsOperationClass.READ_ONLY or not assessment.may_execute:
            raise InstanceInspectionError("inspect_instance did not satisfy the read-only boundary")

        try:
            response = self._client.describe_instances(InstanceIds=[requested_id])
        except Exception as error:
            raise InstanceInspectionError("DescribeInstances observation failed") from error
        response_mapping = _required_mapping(response, "response")
        instance = _single_returned_instance(response_mapping)
        returned_id = _required_string(instance.get("InstanceId"), "InstanceId")
        if returned_id != requested_id:
            raise SandboxTargetMismatchError("Returned instance does not match the requested sandbox")

        tag_key, tag_value = _sandbox_tag(instance, self._target)
        state = _required_mapping(instance.get("State"), "State")
        monitoring = _required_mapping(instance.get("Monitoring"), "Monitoring")
        placement = _required_mapping(instance.get("Placement"), "Placement")
        launch_time = instance.get("LaunchTime")
        if not isinstance(launch_time, datetime):
            raise InstanceInspectionError("DescribeInstances LaunchTime is missing or malformed")
        try:
            return InstanceInspection.create(
                correlation_id=correlation_id,
                instance_id=returned_id,
                region=self._region,
                state=Ec2InstanceState(_required_string(state.get("Name"), "State.Name")),
                instance_type=_required_string(instance.get("InstanceType"), "InstanceType"),
                launch_time=launch_time,
                monitoring_state=Ec2MonitoringState(
                    _required_string(monitoring.get("State"), "Monitoring.State")
                ),
                availability_zone=_required_string(
                    placement.get("AvailabilityZone"),
                    "Placement.AvailabilityZone",
                ),
                sandbox_tag_key=tag_key,
                sandbox_tag_value=tag_value,
            )
        except (ContractValidationError, ValueError) as error:
            raise InstanceInspectionError("DescribeInstances evidence is invalid") from error


def inspection_to_provenance(
    inspection: InstanceInspection,
    *,
    event_id: str,
    sequence: int,
    timestamp: datetime,
) -> ProvenanceRecord:
    """Materialize normalized inspection evidence as append-oriented provenance."""

    if not isinstance(inspection, InstanceInspection):
        raise ContractValidationError("inspection must be an InstanceInspection")
    return ProvenanceRecord(
        correlation_id=inspection.correlation_id,
        event_id=event_id,
        event_type=ProvenanceEventType.CLOUDOPS_INSTANCE_INSPECTED,
        sequence=sequence,
        timestamp=timestamp,
        actor="strands-tool:inspect_instance",
        summary="Inspected configured sandbox EC2 instance",
        evidence_digest=inspection.evidence_digest,
        attributes={
            "authority_gate": inspection.authority_gate.value,
            "aws_api": INSPECT_INSTANCE_AWS_API,
            "instance_id": inspection.instance_id,
            "operation_class": inspection.operation_class.value,
            "region": inspection.region,
            "state": inspection.state.value,
        },
    )

"""Conservative QueryResource implementation for unattached Elastic IP discovery."""

import ipaddress
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Final

from aioa_cloudops_agent.domain.aws_boundary import (
    AwsOperation,
    AwsOperationClass,
    assess_aws_operation,
)
from aioa_cloudops_agent.domain.enums import AuthorityGate
from aioa_cloudops_agent.domain.errors import ContractValidationError, DomainError, ErrorCode
from aioa_cloudops_agent.persistence.models import (
    ProvenanceEventType,
    ProvenanceRecord,
    compute_evidence_digest,
)

from .ec2_readonly import Ec2ReadOnlyClient
from .models import (
    AmbiguousObservation,
    CloudOpsFinding,
    CloudResourceType,
    ElasticIpEvidence,
    FindingType,
    QueryResourceRequest,
    QueryResourceResult,
    compute_ambiguous_observation_digest,
    compute_query_result_digest,
)

ALLOWED_QUERY_OPERATIONS: Final = frozenset({AwsOperation.DESCRIBE_ADDRESSES})
QUERY_AWS_API: Final = "ec2:DescribeAddresses"
_ASSOCIATION_FIELDS: Final = (
    "AssociationId",
    "InstanceId",
    "NetworkInterfaceId",
    "PrivateIpAddress",
)
_AWS_IDENTIFIER_PATTERNS: Final = {
    "AssociationId": re.compile(r"^eipassoc-[0-9a-f]+$"),
    "InstanceId": re.compile(r"^i-[0-9a-f]+$"),
    "NetworkInterfaceId": re.compile(r"^eni-[0-9a-f]+$"),
}
_ALLOCATION_ID_PATTERN: Final = re.compile(r"^eipalloc-[0-9a-f]+$")


class QueryOperationNotAllowedError(DomainError):
    """Raised before any provider call for an operation outside the query allowlist."""

    def __init__(self, operation: AwsOperation) -> None:
        super().__init__(
            code=ErrorCode.CLOUDOPS_QUERY_REJECTED,
            message=f"QueryResource operation is not allowlisted: {operation.value}",
            retryable=False,
        )


class CloudOpsResponseError(DomainError):
    """Raised when the provider response cannot be interpreted safely."""

    def __init__(self, message: str) -> None:
        super().__init__(
            code=ErrorCode.CLOUDOPS_RESPONSE_INVALID,
            message=message,
            retryable=False,
        )


def _safe_reference(address: Mapping[str, Any], index: int) -> str:
    allocation_id = address.get("AllocationId")
    if isinstance(allocation_id, str) and _ALLOCATION_ID_PATTERN.fullmatch(allocation_id):
        return allocation_id
    public_ip = address.get("PublicIp")
    if isinstance(public_ip, str):
        try:
            parsed_public_ip = ipaddress.ip_address(public_ip)
        except ValueError:
            pass
        else:
            if parsed_public_ip.version == 4:
                return public_ip
    return f"response-entry-{index:04d}"


def _ambiguous(
    address: Mapping[str, Any],
    index: int,
    region: str,
    reason: str,
) -> AmbiguousObservation:
    reference = _safe_reference(address, index)
    digest = compute_ambiguous_observation_digest(reference, region, reason)
    return AmbiguousObservation(
        resource_reference=reference,
        region=region,
        reason=reason,
        evidence_digest=digest,
    )


def _classify_address(
    address: Mapping[str, Any],
    index: int,
    region: str,
) -> tuple[CloudOpsFinding | None, AmbiguousObservation | None]:
    public_ip = address.get("PublicIp")
    if not isinstance(public_ip, str) or not public_ip:
        return None, _ambiguous(address, index, region, "PublicIp is missing or malformed")
    try:
        parsed_public_ip = ipaddress.ip_address(public_ip)
    except ValueError:
        return None, _ambiguous(address, index, region, "PublicIp is missing or malformed")
    if parsed_public_ip.version != 4:
        return None, _ambiguous(address, index, region, "PublicIp is missing or malformed")

    allocation_id = address.get("AllocationId")
    if allocation_id is not None and (
        not isinstance(allocation_id, str)
        or _ALLOCATION_ID_PATTERN.fullmatch(allocation_id) is None
    ):
        return None, _ambiguous(address, index, region, "AllocationId is malformed")

    present_association_fields = [field for field in _ASSOCIATION_FIELDS if field in address]
    for field in present_association_fields:
        value = address[field]
        valid_value = isinstance(value, str) and bool(value.strip())
        if valid_value and field == "PrivateIpAddress":
            try:
                valid_value = ipaddress.ip_address(value).version == 4
            except ValueError:
                valid_value = False
        elif valid_value:
            valid_value = _AWS_IDENTIFIER_PATTERNS[field].fullmatch(value) is not None
        if not valid_value:
            return None, _ambiguous(
                address,
                index,
                region,
                f"{field} is present but does not contain a definite association identifier",
            )

    if present_association_fields:
        return None, None

    evidence = ElasticIpEvidence(
        region=region,
        public_ip=public_ip,
        allocation_id=allocation_id,
        association_id=None,
        instance_id=None,
        network_interface_id=None,
        private_ip_address=None,
        classification_reason="No EC2 association fields are present",
    )
    digest = compute_evidence_digest(evidence.as_dict())
    resource_id = allocation_id or public_ip
    return (
        CloudOpsFinding(
            resource_type=CloudResourceType.ELASTIC_IP_ADDRESS,
            resource_id=resource_id,
            region=region,
            finding_type=FindingType.UNATTACHED_ELASTIC_IP,
            summary="Elastic IP allocation has no definite resource association",
            evidence=evidence,
            evidence_digest=digest,
        ),
        None,
    )


class QueryResource:
    """Execute the single allowlisted CloudOps observation without remediation authority."""

    def __init__(self, ec2_client: Ec2ReadOnlyClient) -> None:
        self._ec2_client = ec2_client

    def execute(self, request: QueryResourceRequest) -> QueryResourceResult:
        if not isinstance(request, QueryResourceRequest):
            raise ContractValidationError("request must be a QueryResourceRequest")
        if request.operation not in ALLOWED_QUERY_OPERATIONS:
            raise QueryOperationNotAllowedError(request.operation)

        assessment = assess_aws_operation(request.operation, AuthorityGate.AUTO)
        if (
            assessment.operation_class is not AwsOperationClass.READ_ONLY
            or not assessment.may_execute
        ):
            raise QueryOperationNotAllowedError(request.operation)

        try:
            response = self._ec2_client.describe_addresses()
        except Exception as error:
            raise CloudOpsResponseError("DescribeAddresses observation failed") from error
        if not isinstance(response, Mapping):
            raise CloudOpsResponseError("DescribeAddresses response must be a mapping")

        addresses = response.get("Addresses", [])
        if not isinstance(addresses, list):
            raise CloudOpsResponseError("DescribeAddresses Addresses must be a list")

        findings: list[CloudOpsFinding] = []
        ambiguous: list[AmbiguousObservation] = []
        for index, address in enumerate(addresses, start=1):
            if not isinstance(address, Mapping):
                reason = "Address entry must be a mapping"
                reference = f"response-entry-{index:04d}"
                ambiguous.append(
                    AmbiguousObservation(
                        resource_reference=reference,
                        region=request.region,
                        reason=reason,
                        evidence_digest=compute_ambiguous_observation_digest(
                            reference,
                            request.region,
                            reason,
                        ),
                    )
                )
                continue
            finding, observation = _classify_address(address, index, request.region)
            if finding is not None:
                findings.append(finding)
            if observation is not None:
                ambiguous.append(observation)

        ordered_findings = tuple(sorted(findings, key=lambda item: item.resource_id))
        ordered_ambiguous = tuple(
            sorted(ambiguous, key=lambda item: (item.resource_reference, item.reason))
        )
        result_digest = compute_query_result_digest(
            correlation_id=request.correlation_id,
            region=request.region,
            findings=ordered_findings,
            ambiguous_observations=ordered_ambiguous,
        )
        return QueryResourceResult(
            correlation_id=request.correlation_id,
            operation=request.operation,
            aws_api=QUERY_AWS_API,
            operation_class=AwsOperationClass.READ_ONLY,
            authority_gate=AuthorityGate.AUTO,
            region=request.region,
            findings=ordered_findings,
            ambiguous_observations=ordered_ambiguous,
            evidence_digest=result_digest,
        )


def query_result_to_provenance(
    result: QueryResourceResult,
    *,
    event_id: str,
    sequence: int,
    timestamp: datetime,
) -> ProvenanceRecord:
    """Materialize a completed read-only query as append-oriented provenance."""

    return ProvenanceRecord(
        correlation_id=result.correlation_id,
        event_id=event_id,
        event_type=ProvenanceEventType.CLOUDOPS_QUERY_COMPLETED,
        sequence=sequence,
        timestamp=timestamp,
        actor="cloudops-query-resource",
        summary="Completed read-only unattached Elastic IP observation",
        evidence_digest=result.evidence_digest,
        attributes={
            "ambiguous_count": str(len(result.ambiguous_observations)),
            "authority_gate": result.authority_gate.value,
            "aws_api": result.aws_api,
            "finding_count": str(len(result.findings)),
            "operation_class": result.operation_class.value,
            "region": result.region,
        },
    )

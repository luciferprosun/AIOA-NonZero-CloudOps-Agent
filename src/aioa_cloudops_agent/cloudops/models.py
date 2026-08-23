"""Typed results for narrow, read-only CloudOps observations."""

import ipaddress
import re
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from aioa_cloudops_agent.domain.aws_boundary import AwsOperation, AwsOperationClass
from aioa_cloudops_agent.domain.enums import AuthorityGate
from aioa_cloudops_agent.domain.errors import ContractValidationError
from aioa_cloudops_agent.domain.identifiers import validate_correlation_id
from aioa_cloudops_agent.persistence.models import (
    compute_evidence_digest,
    validate_evidence_digest,
)

_ALLOCATION_ID_PATTERN = re.compile(r"^eipalloc-[0-9a-f]+$")


def _ambiguous_digest_payload(
    resource_reference: str,
    region: str,
    reason: str,
) -> dict[str, str]:
    return {
        "reason": reason,
        "region": region,
        "resource_reference": resource_reference,
    }


class CloudResourceType(StrEnum):
    """Resource types emitted by the current QueryResource contract."""

    ELASTIC_IP_ADDRESS = "AWS_EC2_ELASTIC_IP_ADDRESS"


class FindingType(StrEnum):
    """Closed set of currently supported CloudOps findings."""

    UNATTACHED_ELASTIC_IP = "UNATTACHED_ELASTIC_IP"


@dataclass(frozen=True, slots=True)
class ElasticIpEvidence:
    """Allowlisted non-secret facts used to classify one Elastic IP."""

    region: str
    public_ip: str
    allocation_id: str | None
    association_id: str | None
    instance_id: str | None
    network_interface_id: str | None
    private_ip_address: str | None
    classification_reason: str

    def __post_init__(self) -> None:
        if self.region != "eu-central-1":
            raise ContractValidationError("Elastic IP evidence region must be eu-central-1")
        try:
            parsed_public_ip = ipaddress.ip_address(self.public_ip)
        except ValueError as error:
            raise ContractValidationError("public_ip must be a valid IPv4 address") from error
        if parsed_public_ip.version != 4:
            raise ContractValidationError("public_ip must be a valid IPv4 address")
        if self.allocation_id is not None and _ALLOCATION_ID_PATTERN.fullmatch(
            self.allocation_id
        ) is None:
            raise ContractValidationError("allocation_id must use the eipalloc- prefix")
        for name in (
            "association_id",
            "instance_id",
            "network_interface_id",
            "private_ip_address",
        ):
            if getattr(self, name) is not None:
                raise ContractValidationError(
                    f"unattached Elastic IP evidence must not contain {name}"
                )
        if not isinstance(self.classification_reason, str) or not self.classification_reason:
            raise ContractValidationError("classification_reason must not be empty")

    def as_dict(self) -> dict[str, str | None]:
        """Return only the safe, canonical facts used by the finding."""

        return {
            "allocation_id": self.allocation_id,
            "association_id": self.association_id,
            "classification_reason": self.classification_reason,
            "instance_id": self.instance_id,
            "network_interface_id": self.network_interface_id,
            "private_ip_address": self.private_ip_address,
            "public_ip": self.public_ip,
            "region": self.region,
        }


@dataclass(frozen=True, slots=True)
class CloudOpsFinding:
    """Domain finding that does not leak a raw provider response."""

    resource_type: CloudResourceType
    resource_id: str
    region: str
    finding_type: FindingType
    summary: str
    evidence: ElasticIpEvidence
    evidence_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.resource_type, CloudResourceType):
            raise ContractValidationError("resource_type must be a CloudResourceType")
        if not isinstance(self.resource_id, str) or not self.resource_id:
            raise ContractValidationError("resource_id must not be empty")
        if self.region != "eu-central-1":
            raise ContractValidationError("finding region must be eu-central-1")
        if not isinstance(self.finding_type, FindingType):
            raise ContractValidationError("finding_type must be a FindingType")
        if not isinstance(self.summary, str) or not self.summary:
            raise ContractValidationError("summary must not be empty")
        if not isinstance(self.evidence, ElasticIpEvidence):
            raise ContractValidationError("evidence must be ElasticIpEvidence")
        validate_evidence_digest(self.evidence_digest)
        if self.region != self.evidence.region:
            raise ContractValidationError("finding and evidence regions must match")
        expected_resource_id = self.evidence.allocation_id or self.evidence.public_ip
        if self.resource_id != expected_resource_id:
            raise ContractValidationError("resource_id must match the safe evidence identifier")
        if self.evidence_digest != compute_evidence_digest(self.evidence.as_dict()):
            raise ContractValidationError("evidence_digest does not match finding evidence")


@dataclass(frozen=True, slots=True)
class AmbiguousObservation:
    """Safe evidence that an address could not be classified definitively."""

    resource_reference: str
    region: str
    reason: str
    evidence_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.resource_reference, str) or not self.resource_reference:
            raise ContractValidationError("resource_reference must not be empty")
        if self.region != "eu-central-1":
            raise ContractValidationError("observation region must be eu-central-1")
        if not isinstance(self.reason, str) or not self.reason:
            raise ContractValidationError("reason must not be empty")
        validate_evidence_digest(self.evidence_digest)
        expected_digest = compute_evidence_digest(
            _ambiguous_digest_payload(self.resource_reference, self.region, self.reason)
        )
        if self.evidence_digest != expected_digest:
            raise ContractValidationError(
                "evidence_digest does not match ambiguous observation evidence"
            )


@dataclass(frozen=True, slots=True)
class QueryResourceRequest:
    """One allowlisted provider query under a UUIDv7 execution."""

    correlation_id: UUID
    operation: AwsOperation = AwsOperation.DESCRIBE_ADDRESSES
    region: str = "eu-central-1"

    def __post_init__(self) -> None:
        if not isinstance(self.correlation_id, UUID):
            raise ContractValidationError("correlation_id must be a UUIDv7 value")
        validate_correlation_id(self.correlation_id)
        if not isinstance(self.operation, AwsOperation):
            raise ContractValidationError("operation must be an AwsOperation")
        if self.region != "eu-central-1":
            raise ContractValidationError("QueryResource region must be eu-central-1")


@dataclass(frozen=True, slots=True)
class QueryResourceResult:
    """Deterministic query outcome ready for provenance materialization."""

    correlation_id: UUID
    operation: AwsOperation
    aws_api: str
    operation_class: AwsOperationClass
    authority_gate: AuthorityGate
    region: str
    findings: tuple[CloudOpsFinding, ...]
    ambiguous_observations: tuple[AmbiguousObservation, ...]
    evidence_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.correlation_id, UUID):
            raise ContractValidationError("correlation_id must be a UUIDv7 value")
        validate_correlation_id(self.correlation_id)
        if self.operation is not AwsOperation.DESCRIBE_ADDRESSES:
            raise ContractValidationError("result operation must be DESCRIBE_ADDRESSES")
        if self.aws_api != "ec2:DescribeAddresses":
            raise ContractValidationError("result aws_api must be ec2:DescribeAddresses")
        if self.operation_class is not AwsOperationClass.READ_ONLY:
            raise ContractValidationError("QueryResource result must be READ_ONLY")
        if self.authority_gate is not AuthorityGate.AUTO:
            raise ContractValidationError("QueryResource result authority gate must be AUTO")
        if self.region != "eu-central-1":
            raise ContractValidationError("result region must be eu-central-1")
        if not isinstance(self.findings, tuple) or not all(
            isinstance(finding, CloudOpsFinding) for finding in self.findings
        ):
            raise ContractValidationError("findings must be typed CloudOpsFinding values")
        if not isinstance(self.ambiguous_observations, tuple) or not all(
            isinstance(observation, AmbiguousObservation)
            for observation in self.ambiguous_observations
        ):
            raise ContractValidationError(
                "ambiguous_observations must be typed AmbiguousObservation values"
            )
        validate_evidence_digest(self.evidence_digest)
        if self.findings != tuple(sorted(self.findings, key=lambda item: item.resource_id)):
            raise ContractValidationError("findings must use deterministic resource ordering")
        if self.ambiguous_observations != tuple(
            sorted(
                self.ambiguous_observations,
                key=lambda item: (item.resource_reference, item.reason),
            )
        ):
            raise ContractValidationError(
                "ambiguous_observations must use deterministic resource ordering"
            )
        if len({finding.resource_id for finding in self.findings}) != len(self.findings):
            raise ContractValidationError("findings must not duplicate a resource identifier")
        if self.evidence_digest != compute_query_result_digest(
            correlation_id=self.correlation_id,
            region=self.region,
            findings=self.findings,
            ambiguous_observations=self.ambiguous_observations,
        ):
            raise ContractValidationError("evidence_digest does not match query result evidence")


def compute_ambiguous_observation_digest(
    resource_reference: str,
    region: str,
    reason: str,
) -> str:
    """Return the canonical digest for one ambiguity record."""

    return compute_evidence_digest(_ambiguous_digest_payload(resource_reference, region, reason))


def compute_query_result_digest(
    *,
    correlation_id: UUID,
    region: str,
    findings: tuple[CloudOpsFinding, ...],
    ambiguous_observations: tuple[AmbiguousObservation, ...],
) -> str:
    """Return the canonical aggregate digest for one completed query."""

    return compute_evidence_digest(
        {
            "ambiguous": [
                {
                    "evidence_digest": item.evidence_digest,
                    "reason": item.reason,
                    "resource_reference": item.resource_reference,
                }
                for item in ambiguous_observations
            ],
            "authority_gate": AuthorityGate.AUTO.value,
            "aws_api": "ec2:DescribeAddresses",
            "correlation_id": str(correlation_id),
            "findings": [
                {
                    "evidence_digest": item.evidence_digest,
                    "finding_type": item.finding_type.value,
                    "resource_id": item.resource_id,
                }
                for item in findings
            ],
            "operation_class": AwsOperationClass.READ_ONLY.value,
            "region": region,
        }
    )

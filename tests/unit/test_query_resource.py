from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from aioa_cloudops_agent.cloudops import (
    AmbiguousObservation,
    CloudOpsResponseError,
    FindingType,
    QueryOperationNotAllowedError,
    QueryResource,
    QueryResourceRequest,
    compute_ambiguous_observation_digest,
    query_result_to_provenance,
)
from aioa_cloudops_agent.domain import (
    AuthorityGate,
    AwsOperation,
    AwsOperationClass,
    ContractValidationError,
)
from aioa_cloudops_agent.persistence import ProvenanceEventType

UUID7 = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3a")
NOW = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)


class FakeEc2Client:
    def __init__(self, response: object) -> None:
        self.response = response
        self.describe_calls = 0
        self.release_calls = 0

    def describe_addresses(self) -> Any:
        self.describe_calls += 1
        return self.response

    def release_address(self, **_kwargs: object) -> None:
        self.release_calls += 1
        raise AssertionError("remediation must not be invoked")


def _execute(response: object):
    client = FakeEc2Client(response)
    result = QueryResource(client).execute(QueryResourceRequest(UUID7))
    return client, result


def test_attached_elastic_ip_is_not_reported_as_unattached() -> None:
    client, result = _execute(
        {
            "Addresses": [
                {
                    "AllocationId": "eipalloc-001",
                    "AssociationId": "eipassoc-001",
                    "InstanceId": "i-001",
                    "PublicIp": "198.51.100.10",
                }
            ]
        }
    )

    assert result.findings == ()
    assert result.ambiguous_observations == ()
    assert client.describe_calls == 1
    assert client.release_calls == 0


def test_clearly_unattached_elastic_ip_is_reported_with_typed_evidence() -> None:
    _client, result = _execute(
        {"Addresses": [{"AllocationId": "eipalloc-002", "PublicIp": "198.51.100.20"}]}
    )

    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.finding_type is FindingType.UNATTACHED_ELASTIC_IP
    assert finding.resource_id == "eipalloc-002"
    assert finding.evidence.allocation_id == "eipalloc-002"
    assert finding.evidence.association_id is None
    assert len(finding.evidence_digest) == 64


def test_multiple_addresses_are_classified_conservatively() -> None:
    _client, result = _execute(
        {
            "Addresses": [
                {"AllocationId": "eipalloc-003", "PublicIp": "198.51.100.30"},
                {
                    "AllocationId": "eipalloc-004",
                    "NetworkInterfaceId": "eni-004",
                    "PublicIp": "198.51.100.40",
                },
                {
                    "AllocationId": "eipalloc-005",
                    "AssociationId": None,
                    "PublicIp": "198.51.100.50",
                },
            ]
        }
    )

    assert [finding.resource_id for finding in result.findings] == ["eipalloc-003"]
    assert len(result.ambiguous_observations) == 1
    assert result.ambiguous_observations[0].resource_reference == "eipalloc-005"


@pytest.mark.parametrize("response", [{}, {"Addresses": []}])
def test_empty_provider_response_returns_empty_typed_result(response: object) -> None:
    _client, result = _execute(response)

    assert result.findings == ()
    assert result.ambiguous_observations == ()


@pytest.mark.parametrize(
    "address",
    [
        {},
        {"AllocationId": "bad", "PublicIp": "198.51.100.60"},
        {"AllocationId": "eipalloc-006", "PublicIp": "not-an-ip"},
        "not-a-mapping",
    ],
)
def test_malformed_address_is_explicitly_ambiguous(address: object) -> None:
    _client, result = _execute({"Addresses": [address]})

    assert result.findings == ()
    assert len(result.ambiguous_observations) == 1
    assert result.ambiguous_observations[0].reason


@pytest.mark.parametrize("response", [None, [], {"Addresses": None}, {"Addresses": {}}])
def test_malformed_top_level_response_raises_typed_error(response: object) -> None:
    client = FakeEc2Client(response)

    with pytest.raises(CloudOpsResponseError):
        QueryResource(client).execute(QueryResourceRequest(UUID7))


def test_ambiguous_observation_rejects_a_mismatched_digest() -> None:
    reason = "AssociationId is malformed"
    valid_digest = compute_ambiguous_observation_digest(
        "eipalloc-006",
        "eu-central-1",
        reason,
    )

    with pytest.raises(ContractValidationError, match="does not match"):
        AmbiguousObservation(
            resource_reference="eipalloc-006",
            region="eu-central-1",
            reason=reason,
            evidence_digest="0" * 64 if valid_digest != "0" * 64 else "1" * 64,
        )


def test_query_is_read_only_auto_and_preserves_uuid7() -> None:
    _client, result = _execute({})

    assert result.correlation_id == UUID7
    assert result.correlation_id.version == 7
    assert result.operation_class is AwsOperationClass.READ_ONLY
    assert result.authority_gate is AuthorityGate.AUTO
    assert result.aws_api == "ec2:DescribeAddresses"


def test_query_request_requires_typed_uuid7() -> None:
    with pytest.raises(ContractValidationError, match="UUIDv7"):
        QueryResourceRequest(str(UUID7))


def test_evidence_digest_is_deterministic_across_provider_ordering() -> None:
    addresses = [
        {"AllocationId": "eipalloc-010", "PublicIp": "198.51.100.10"},
        {"AllocationId": "eipalloc-020", "PublicIp": "198.51.100.20"},
    ]

    _client, first = _execute({"Addresses": addresses})
    _client, second = _execute({"Addresses": list(reversed(addresses))})

    assert first.evidence_digest == second.evidence_digest
    assert [finding.evidence_digest for finding in first.findings] == [
        finding.evidence_digest for finding in second.findings
    ]


def test_mutating_operation_is_rejected_before_provider_invocation() -> None:
    client = FakeEc2Client({})
    request = QueryResourceRequest(UUID7, operation=AwsOperation.RELEASE_ADDRESS)

    with pytest.raises(QueryOperationNotAllowedError):
        QueryResource(client).execute(request)

    assert client.describe_calls == 0
    assert client.release_calls == 0


def test_findings_do_not_leak_credentials_account_data_or_raw_response() -> None:
    confidential_marker = "must-not-leak"
    _client, result = _execute(
        {
            "Addresses": [
                {
                    "AllocationId": "eipalloc-030",
                    "PublicIp": "198.51.100.30",
                    "OwnerId": "owner-account-marker",
                    "SecretAccessKey": confidential_marker,
                    "SessionToken": confidential_marker,
                    "Tags": [{"Key": "Password", "Value": confidential_marker}],
                }
            ],
            "ResponseMetadata": {"RequestId": confidential_marker},
        }
    )

    serialized = repr(result)
    assert confidential_marker not in serialized
    assert "owner-account-marker" not in serialized
    assert "OwnerId" not in serialized
    assert "ResponseMetadata" not in serialized
    assert not hasattr(result, "raw_response")
    assert set(asdict(result.findings[0].evidence)) == {
        "allocation_id",
        "association_id",
        "classification_reason",
        "instance_id",
        "network_interface_id",
        "private_ip_address",
        "public_ip",
        "region",
    }


def test_completed_query_materializes_append_oriented_provenance() -> None:
    _client, result = _execute(
        {"Addresses": [{"AllocationId": "eipalloc-040", "PublicIp": "198.51.100.40"}]}
    )

    event = query_result_to_provenance(
        result,
        event_id="query-001",
        sequence=2,
        timestamp=NOW,
    )

    assert event.correlation_id == UUID7
    assert event.event_type is ProvenanceEventType.CLOUDOPS_QUERY_COMPLETED
    assert event.evidence_digest == result.evidence_digest
    assert event.attributes["aws_api"] == "ec2:DescribeAddresses"
    assert event.attributes["operation_class"] == "READ_ONLY"
    assert event.attributes["authority_gate"] == "AUTO"

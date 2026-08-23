from datetime import UTC, datetime
from typing import Any

import pytest

from aioa_cloudops_agent.cloudops import (
    Ec2InstanceState,
    Ec2MonitoringState,
    InspectInstanceService,
    InstanceInspection,
    InstanceInspectionError,
    SandboxTarget,
    SandboxTargetMismatchError,
    inspection_to_provenance,
)
from aioa_cloudops_agent.domain import (
    AuthorityGate,
    AwsOperationClass,
    ContractValidationError,
    generate_correlation_id,
)
from aioa_cloudops_agent.persistence import ProvenanceEventType

INSTANCE_ID = "i-0123456789abcdef0"
OTHER_INSTANCE_ID = "i-0fedcba9876543210"
LAUNCH_TIME = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)


def _instance(*, instance_id: str = INSTANCE_ID, tags: object = None) -> dict[str, Any]:
    return {
        "InstanceId": instance_id,
        "State": {"Name": "running"},
        "InstanceType": "t3.micro",
        "LaunchTime": LAUNCH_TIME,
        "Monitoring": {"State": "disabled"},
        "Placement": {"AvailabilityZone": "eu-central-1a"},
        "Tags": (
            [{"Key": "AIOACloudOpsSandbox", "Value": "true"}]
            if tags is None
            else tags
        ),
        "OwnerId": "owner-marker",
        "CredentialMaterial": "must-not-leak",
    }


def _response(*instances: object) -> dict[str, object]:
    return {"Reservations": [{"Instances": list(instances)}]}


class RecordingEc2Client:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[list[str]] = []

    def describe_instances(self, *, InstanceIds: list[str]) -> object:
        self.calls.append(InstanceIds)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _service(response: object) -> tuple[InspectInstanceService, RecordingEc2Client]:
    client = RecordingEc2Client(response)
    return InspectInstanceService(client, SandboxTarget(INSTANCE_ID)), client


def test_inspection_requests_exact_target_and_returns_typed_safe_result() -> None:
    service, client = _service(_response(_instance()))
    correlation_id = generate_correlation_id()

    result = service.inspect(instance_id=INSTANCE_ID, correlation_id=correlation_id)

    assert client.calls == [[INSTANCE_ID]]
    assert isinstance(result, InstanceInspection)
    assert result.correlation_id == correlation_id
    assert result.instance_id == INSTANCE_ID
    assert result.state is Ec2InstanceState.RUNNING
    assert result.instance_type == "t3.micro"
    assert result.monitoring_state is Ec2MonitoringState.DISABLED
    assert result.authority_gate is AuthorityGate.AUTO
    assert result.operation_class is AwsOperationClass.READ_ONLY
    assert "Reservations" not in result.as_dict()
    assert "OwnerId" not in result.as_dict()
    assert "CredentialMaterial" not in result.as_dict()
    assert "must-not-leak" not in repr(result.as_dict())
    assert "owner-marker" not in repr(result.as_dict())


def test_inspection_evidence_digest_is_deterministic() -> None:
    service, _ = _service(_response(_instance()))
    correlation_id = generate_correlation_id()

    first = service.inspect(instance_id=INSTANCE_ID, correlation_id=correlation_id)
    second = service.inspect(instance_id=INSTANCE_ID, correlation_id=correlation_id)

    assert first.evidence_digest == second.evidence_digest
    assert len(first.evidence_digest) == 64


def test_request_for_nonconfigured_instance_fails_before_provider_call() -> None:
    service, client = _service(_response(_instance()))

    with pytest.raises(SandboxTargetMismatchError, match="not the configured sandbox"):
        service.inspect(instance_id=OTHER_INSTANCE_ID, correlation_id=generate_correlation_id())

    assert client.calls == []


def test_returned_instance_must_match_exact_requested_target() -> None:
    service, client = _service(_response(_instance(instance_id=OTHER_INSTANCE_ID)))

    with pytest.raises(SandboxTargetMismatchError, match="does not match"):
        service.inspect(instance_id=INSTANCE_ID, correlation_id=generate_correlation_id())

    assert client.calls == [[INSTANCE_ID]]


@pytest.mark.parametrize(
    "tags",
    [
        [],
        [{"Key": "AIOACloudOpsSandbox", "Value": "false"}],
        [
            {"Key": "AIOACloudOpsSandbox", "Value": "true"},
            {"Key": "AIOACloudOpsSandbox", "Value": "true"},
        ],
        [{"Key": "Name", "Value": "sandbox"}],
    ],
)
def test_missing_ambiguous_or_wrong_sandbox_tag_fails_closed(tags: object) -> None:
    service, _ = _service(_response(_instance(tags=tags)))

    with pytest.raises(SandboxTargetMismatchError):
        service.inspect(instance_id=INSTANCE_ID, correlation_id=generate_correlation_id())


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"Reservations": None},
        _response(),
        _response(_instance(), _instance()),
        {"Reservations": [{"Instances": None}]},
        _response({**_instance(), "State": {"Name": "unknown"}}),
        _response({**_instance(), "LaunchTime": "not-a-datetime"}),
    ],
)
def test_ambiguous_or_malformed_provider_evidence_fails_explicitly(response: object) -> None:
    service, _ = _service(response)

    with pytest.raises(InstanceInspectionError):
        service.inspect(instance_id=INSTANCE_ID, correlation_id=generate_correlation_id())


def test_provider_failure_is_translated_without_leaking_details() -> None:
    service, _ = _service(RuntimeError("provider-secret-detail"))

    with pytest.raises(InstanceInspectionError, match="observation failed") as captured:
        service.inspect(instance_id=INSTANCE_ID, correlation_id=generate_correlation_id())

    assert "provider-secret-detail" not in str(captured.value)


@pytest.mark.parametrize("instance_id", [None, "", "i-anything", "I-0123456789abcdef0"])
def test_malformed_instance_identifier_fails_explicitly(instance_id: object) -> None:
    with pytest.raises(ContractValidationError, match="valid EC2 instance"):
        SandboxTarget(instance_id)


def test_missing_production_sandbox_configuration_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SANDBOX_INSTANCE_ID", raising=False)

    with pytest.raises(ContractValidationError, match="SANDBOX_INSTANCE_ID is required"):
        SandboxTarget.from_environment()


def test_inspection_materializes_append_oriented_provenance() -> None:
    service, _ = _service(_response(_instance()))
    inspection = service.inspect(
        instance_id=INSTANCE_ID,
        correlation_id=generate_correlation_id(),
    )

    event = inspection_to_provenance(
        inspection,
        event_id="evt-inspection-1",
        sequence=1,
        timestamp=datetime(2026, 8, 23, 9, 1, tzinfo=UTC),
    )

    assert event.correlation_id == inspection.correlation_id
    assert event.event_type is ProvenanceEventType.CLOUDOPS_INSTANCE_INSPECTED
    assert event.evidence_digest == inspection.evidence_digest
    assert event.attributes["aws_api"] == "ec2:DescribeInstances"
    assert event.attributes["operation_class"] == "READ_ONLY"

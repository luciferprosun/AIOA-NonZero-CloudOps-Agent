from contextlib import AbstractContextManager
from datetime import UTC, datetime

import pytest

from aioa_cloudops_agent.agent import build_agent_trace_attributes, build_inspection_request
from aioa_cloudops_agent.cloudops import (
    InspectInstanceService,
    SandboxTarget,
    create_inspect_instance_tool,
    inspection_to_provenance,
)
from aioa_cloudops_agent.domain import ContractValidationError, generate_correlation_id

INSTANCE_ID = "i-0123456789abcdef0"


class FakeEc2Client:
    def describe_instances(self, *, InstanceIds: list[str]) -> dict[str, object]:
        assert InstanceIds == [INSTANCE_ID]
        return {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": INSTANCE_ID,
                            "State": {"Name": "running"},
                            "InstanceType": "t3.micro",
                            "LaunchTime": datetime(2026, 8, 23, 9, 0, tzinfo=UTC),
                            "Monitoring": {"State": "disabled"},
                            "Placement": {"AvailabilityZone": "eu-central-1a"},
                            "Tags": [
                                {"Key": "AIOACloudOpsSandbox", "Value": "true"}
                            ],
                        }
                    ]
                }
            ]
        }


class RecordingSpan:
    def __init__(self) -> None:
        self.attributes: dict[str, object] = {}

    def set_attribute(self, name: str, value: object) -> None:
        self.attributes[name] = value


class SpanContext(AbstractContextManager[RecordingSpan]):
    def __init__(self, span: RecordingSpan) -> None:
        self.span = span

    def __enter__(self) -> RecordingSpan:
        return self.span

    def __exit__(self, *args: object) -> None:
        return None


class RecordingTracer:
    def __init__(self) -> None:
        self.span_names: list[str] = []
        self.spans: list[RecordingSpan] = []

    def start_as_current_span(self, name: str) -> SpanContext:
        self.span_names.append(name)
        span = RecordingSpan()
        self.spans.append(span)
        return SpanContext(span)


def test_agent_trace_attributes_propagate_uuidv7_correlation() -> None:
    correlation_id = generate_correlation_id()

    attributes = build_agent_trace_attributes(correlation_id)

    assert attributes["aioa.correlation_id"] == str(correlation_id)
    assert attributes["aioa.agent_id"] == "aioa-nonzero-cloudops-primary"
    assert attributes["aioa.authority_gate"] == "AUTO"
    assert attributes["aioa.operation_class"] == "READ_ONLY"


def test_native_tool_emits_safe_trace_and_typed_result() -> None:
    correlation_id = generate_correlation_id()
    tracer = RecordingTracer()
    service = InspectInstanceService(FakeEc2Client(), SandboxTarget(INSTANCE_ID))
    inspect_instance = create_inspect_instance_tool(service, correlation_id, tracer=tracer)

    result = inspect_instance(instance_id=INSTANCE_ID)

    assert inspect_instance.tool_name == "inspect_instance"
    assert result["correlation_id"] == str(correlation_id)
    assert result["instance_id"] == INSTANCE_ID
    assert result["authority_gate"] == "AUTO"
    assert result["operation_class"] == "READ_ONLY"
    assert tracer.span_names == ["cloudops.inspect_instance"]
    assert tracer.spans[0].attributes["aioa.correlation_id"] == str(correlation_id)
    assert tracer.spans[0].attributes["aioa.tool_name"] == "inspect_instance"
    assert tracer.spans[0].attributes["aioa.evidence_digest"] == result["evidence_digest"]


def test_tool_result_and_provenance_retain_same_correlation_and_digest() -> None:
    correlation_id = generate_correlation_id()
    service = InspectInstanceService(FakeEc2Client(), SandboxTarget(INSTANCE_ID))
    inspection = service.inspect(instance_id=INSTANCE_ID, correlation_id=correlation_id)
    event = inspection_to_provenance(
        inspection,
        event_id="evt-tool-1",
        sequence=1,
        timestamp=datetime(2026, 8, 23, 9, 1, tzinfo=UTC),
    )

    assert event.correlation_id == correlation_id
    assert event.evidence_digest == inspection.evidence_digest
    assert event.attributes["instance_id"] == INSTANCE_ID


def test_malformed_tool_input_fails_explicitly() -> None:
    service = InspectInstanceService(FakeEc2Client(), SandboxTarget(INSTANCE_ID))
    inspect_instance = create_inspect_instance_tool(service, generate_correlation_id())

    with pytest.raises(ContractValidationError, match="valid EC2 instance"):
        inspect_instance(instance_id="not-an-instance")


def test_inspection_request_forces_one_tool_and_no_mutation_claim() -> None:
    request = build_inspection_request(SandboxTarget(INSTANCE_ID))

    assert "inspect_instance exactly once" in request
    assert INSTANCE_ID in request
    assert "only on the returned evidence" in request
    assert "Do not claim or propose any mutation" in request


def test_untyped_request_target_fails_explicitly() -> None:
    with pytest.raises(ContractValidationError, match="SandboxTarget"):
        build_inspection_request(INSTANCE_ID)

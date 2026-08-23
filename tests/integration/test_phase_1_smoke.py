import copy
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from aioa_cloudops_agent.cloudops import (
    QueryOperationNotAllowedError,
    QueryResource,
    QueryResourceRequest,
    query_result_to_provenance,
)
from aioa_cloudops_agent.domain import (
    AuthorityGate,
    AwsBoundaryViolationError,
    AwsOperation,
    ExecutionBudget,
    ExecutionContext,
    ExecutionState,
    assess_aws_operation,
    generate_correlation_id,
)
from aioa_cloudops_agent.persistence import (
    DynamoDbExecutionRepository,
    ExecutionRecord,
    IdempotencyClaim,
    ProvenanceEventType,
    claim_once,
)

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


class ConditionalCheckFailed(Exception):
    def __init__(self) -> None:
        self.response = {"Error": {"Code": "ConditionalCheckFailedException"}}
        super().__init__("conditional write rejected")


class LocalDynamoDbClient:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, Any]] = {}

    @staticmethod
    def _key(value: dict[str, Any]) -> tuple[str, str]:
        return value["PK"]["S"], value["SK"]["S"]

    def put_item(self, **kwargs: Any) -> dict[str, Any]:
        item = kwargs["Item"]
        key = self._key(item)
        if kwargs["ConditionExpression"].startswith("attribute_not_exists") and key in self.items:
            raise ConditionalCheckFailed
        self.items[key] = copy.deepcopy(item)
        return {}

    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        item = self.items.get(self._key(kwargs["Key"]))
        return {} if item is None else {"Item": copy.deepcopy(item)}

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        item = self.items[self._key(kwargs["Key"])]
        values = kwargs["ExpressionAttributeValues"]
        if (
            item["version"] != values[":expected_version"]
            or item["execution_state"] != values[":current_state"]
        ):
            raise ConditionalCheckFailed
        item["execution_state"] = copy.deepcopy(values[":next_state"])
        item["updated_at"] = copy.deepcopy(values[":updated_at"])
        item["version"] = {"N": str(int(item["version"]["N"]) + 1)}
        return {"Attributes": copy.deepcopy(item)}


class LocalEc2Client:
    def __init__(self) -> None:
        self.describe_calls = 0

    def describe_addresses(self) -> dict[str, object]:
        self.describe_calls += 1
        return {
            "Addresses": [
                {
                    "AllocationId": "eipalloc-a11ce",
                    "PublicIp": "198.51.100.42",
                }
            ]
        }


def test_phase_1_components_compose_without_network_or_cloud_writes() -> None:
    correlation_id = generate_correlation_id()
    context = ExecutionContext(
        correlation_id=correlation_id,
        idempotency_key="phase-1-smoke",
        state=ExecutionState.INIT,
        authority_gate=AuthorityGate.AUTO,
        budget=ExecutionBudget(max_turns=5, max_tokens=1_024),
    )
    dynamodb_client = LocalDynamoDbClient()
    repository = DynamoDbExecutionRepository(dynamodb_client, "local-phase-1-state")

    claim_once(
        repository,
        IdempotencyClaim(
            correlation_id=context.correlation_id,
            idempotency_key=context.idempotency_key,
            claimed_at=NOW,
        ),
    )
    repository.create_execution(
        ExecutionRecord(
            correlation_id=context.correlation_id,
            idempotency_key=context.idempotency_key,
            execution_state=context.state,
            authority_gate=context.authority_gate,
            created_at=NOW,
            updated_at=NOW,
            version=1,
        )
    )
    running = repository.update_execution_state(
        context.correlation_id,
        ExecutionState.RUNNING,
        expected_version=1,
        updated_at=NOW + timedelta(seconds=1),
    )

    ec2_client = LocalEc2Client()
    query_result = QueryResource(ec2_client).execute(
        QueryResourceRequest(context.correlation_id)
    )
    provenance = query_result_to_provenance(
        query_result,
        event_id="cloudops-query-001",
        sequence=1,
        timestamp=NOW + timedelta(seconds=2),
    )
    repository.append_provenance(provenance)
    success = repository.update_execution_state(
        context.correlation_id,
        ExecutionState.SUCCESS,
        expected_version=running.version,
        updated_at=NOW + timedelta(seconds=3),
    )

    assert correlation_id.version == 7
    assert ec2_client.describe_calls == 1
    assert [finding.resource_id for finding in query_result.findings] == ["eipalloc-a11ce"]
    assert len(query_result.evidence_digest) == 64
    assert provenance.event_type is ProvenanceEventType.CLOUDOPS_QUERY_COMPLETED
    assert provenance.evidence_digest == query_result.evidence_digest
    assert success.execution_state is ExecutionState.SUCCESS
    assert success.version == 3
    assert repository.get_execution(correlation_id) == success
    assert {item["entity_type"]["S"] for item in dynamodb_client.items.values()} == {
        "EXECUTION",
        "IDEMPOTENCY",
        "PROVENANCE",
    }


def test_phase_1_mutation_attempt_is_rejected_before_provider_call() -> None:
    correlation_id = generate_correlation_id()
    ec2_client = LocalEc2Client()

    with pytest.raises(AwsBoundaryViolationError):
        assess_aws_operation(AwsOperation.RELEASE_ADDRESS, AuthorityGate.AUTO)
    with pytest.raises(QueryOperationNotAllowedError):
        QueryResource(ec2_client).execute(
            QueryResourceRequest(
                correlation_id,
                operation=AwsOperation.RELEASE_ADDRESS,
            )
        )

    assert ec2_client.describe_calls == 0

"""Non-Zero persistence contracts and DynamoDB adapter."""

from .dynamodb import DynamoDbClient, DynamoDbExecutionRepository
from .errors import (
    IdempotencyConflictError,
    OptimisticConcurrencyError,
    PersistenceConflictError,
    PersistenceOperationError,
)
from .idempotency import claim_once
from .keys import (
    DynamoKey,
    approval_key,
    execution_key,
    idempotency_key,
    provenance_key,
)
from .models import (
    ExecutionRecord,
    IdempotencyClaim,
    ProvenanceEventType,
    ProvenanceRecord,
    compute_evidence_digest,
    validate_evidence_digest,
    validate_utc_timestamp,
)
from .repository import ExecutionRepository

__all__ = [
    "DynamoDbClient",
    "DynamoDbExecutionRepository",
    "DynamoKey",
    "ExecutionRecord",
    "ExecutionRepository",
    "IdempotencyClaim",
    "IdempotencyConflictError",
    "OptimisticConcurrencyError",
    "PersistenceConflictError",
    "PersistenceOperationError",
    "ProvenanceEventType",
    "ProvenanceRecord",
    "approval_key",
    "claim_once",
    "compute_evidence_digest",
    "execution_key",
    "idempotency_key",
    "provenance_key",
    "validate_evidence_digest",
    "validate_utc_timestamp",
]

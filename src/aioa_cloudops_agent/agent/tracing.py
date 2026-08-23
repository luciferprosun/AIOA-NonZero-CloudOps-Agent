"""Correlation attributes shared by Strands, model, tool, and provenance spans."""

from typing import Final
from uuid import UUID

from aioa_cloudops_agent.domain.errors import ContractValidationError
from aioa_cloudops_agent.domain.identifiers import validate_correlation_id

PRIMARY_AGENT_ID: Final = "aioa-nonzero-cloudops-primary"


def build_agent_trace_attributes(correlation_id: UUID) -> dict[str, str]:
    """Return safe OpenTelemetry attributes inherited by the Strands invocation."""

    if not isinstance(correlation_id, UUID):
        raise ContractValidationError("correlation_id must be a UUIDv7 value")
    valid_id = validate_correlation_id(correlation_id)
    return {
        "aioa.agent_id": PRIMARY_AGENT_ID,
        "aioa.authority_gate": "AUTO",
        "aioa.correlation_id": str(valid_id),
        "aioa.operation_class": "READ_ONLY",
    }

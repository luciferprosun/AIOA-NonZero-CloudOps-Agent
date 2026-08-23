"""Native Strands tool registration for canonical EC2 inspection."""

from typing import Final
from uuid import UUID

from opentelemetry import trace
from opentelemetry.trace import Tracer
from strands import tool
from strands.tools.decorator import DecoratedFunctionTool

from aioa_cloudops_agent.domain.errors import ContractValidationError
from aioa_cloudops_agent.domain.identifiers import validate_correlation_id

from .inspect_instance import InspectInstanceService

INSPECT_INSTANCE_TOOL_NAME: Final = "inspect_instance"


def create_inspect_instance_tool(
    service: InspectInstanceService,
    correlation_id: UUID,
    *,
    tracer: Tracer | None = None,
) -> DecoratedFunctionTool:
    """Bind one execution correlation ID to the only active Strands tool."""

    if not isinstance(correlation_id, UUID):
        raise ContractValidationError("correlation_id must be a UUIDv7 value")
    validate_correlation_id(correlation_id)
    active_tracer = tracer or trace.get_tracer("aioa_cloudops_agent.cloudops")

    @tool(name=INSPECT_INSTANCE_TOOL_NAME)
    def inspect_instance(instance_id: str) -> dict[str, str]:
        """Inspect exactly one configured sandbox EC2 instance using read-only evidence."""

        with active_tracer.start_as_current_span("cloudops.inspect_instance") as span:
            span.set_attribute("aioa.correlation_id", str(correlation_id))
            span.set_attribute("aioa.tool_name", INSPECT_INSTANCE_TOOL_NAME)
            span.set_attribute("aioa.authority_gate", "AUTO")
            span.set_attribute("aioa.operation_class", "READ_ONLY")
            inspection = service.inspect(
                instance_id=instance_id,
                correlation_id=correlation_id,
            )
            span.set_attribute("aioa.evidence_digest", inspection.evidence_digest)
            span.set_attribute("aws.region", inspection.region)
            return inspection.as_dict()

    return inspect_instance

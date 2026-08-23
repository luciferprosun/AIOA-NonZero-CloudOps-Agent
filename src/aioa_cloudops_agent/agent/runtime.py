"""Bounded invocation request construction for the primary agent."""

from aioa_cloudops_agent.cloudops.models import SandboxTarget
from aioa_cloudops_agent.domain.errors import ContractValidationError


def build_inspection_request(target: SandboxTarget) -> str:
    """Require one canonical tool call before an evidence-based conclusion."""

    if not isinstance(target, SandboxTarget):
        raise ContractValidationError("target must be a SandboxTarget")
    return (
        "Use inspect_instance exactly once for instance_id "
        f"{target.instance_id}. Base the conclusion only on the returned evidence. "
        "Do not claim or propose any mutation."
    )

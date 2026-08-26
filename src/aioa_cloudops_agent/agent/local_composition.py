"""Safe local composition using the same NZ contracts and adapter interfaces."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from aioa_cloudops_agent.cloudops import MockAwsAdapter, PlanRemediation, QueryResource
from aioa_cloudops_agent.config import LocalFirstMode, LocalFirstSettings
from aioa_cloudops_agent.domain.errors import ContractValidationError
from aioa_cloudops_agent.nz import generate_event_id, generate_proposal_id
from aioa_cloudops_agent.persistence import LocalFileDurableTruthRepository
from aioa_cloudops_agent.providers import MockModelProvider

from .local_first import LocalFirstPhaseOneFlow


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class LocalFirstRuntime:
    """Inspectable dependencies for one credential-free local composition."""

    flow: LocalFirstPhaseOneFlow
    repository: LocalFileDurableTruthRepository
    cloud_provider: MockAwsAdapter
    model_provider: MockModelProvider


def create_local_first_runtime(
    settings: LocalFirstSettings | None = None,
    *,
    clock: Callable[[], datetime] = _utc_now,
    proposal_id_factory: Callable[[], UUID] = generate_proposal_id,
    event_id_factory: Callable[[], UUID] = generate_event_id,
) -> LocalFirstRuntime:
    """Compose mock mode or fail explicitly when unavailable live mode is requested."""

    selected = settings or LocalFirstSettings()
    if not isinstance(selected, LocalFirstSettings):
        raise ContractValidationError("settings must be LocalFirstSettings")
    if selected.mode is not LocalFirstMode.MOCK:
        raise ContractValidationError(
            "live Local-First composition is unavailable; no mock fallback was selected"
        )
    cloud_provider = MockAwsAdapter()
    model_provider = MockModelProvider()
    repository = LocalFileDurableTruthRepository(selected.state_path)
    flow = LocalFirstPhaseOneFlow(
        query_resource=QueryResource(cloud_provider),
        plan_remediation=PlanRemediation(),
        model_provider=model_provider,
        repository=repository,
        clock=clock,
        proposal_id_factory=proposal_id_factory,
        event_id_factory=event_id_factory,
    )
    return LocalFirstRuntime(
        flow=flow,
        repository=repository,
        cloud_provider=cloud_provider,
        model_provider=model_provider,
    )

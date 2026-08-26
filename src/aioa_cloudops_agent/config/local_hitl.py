"""Safe-by-default Local-2 state, inventory, and approval challenge settings."""

import os
from dataclasses import dataclass
from pathlib import Path

from aioa_cloudops_agent.domain.errors import ContractValidationError

from .local_first import LocalFirstMode


@dataclass(frozen=True, slots=True)
class LocalHitlSettings:
    """Non-secret settings for the complete credential-free Local-2 runtime."""

    mode: LocalFirstMode = LocalFirstMode.MOCK
    state_path: Path = Path(".local/aioa-local-hitl-state.json")
    inventory_path: Path = Path(".local/aioa-local-mock-inventory.json")
    request_ttl_seconds: int = 600

    def __post_init__(self) -> None:
        if self.mode is not LocalFirstMode.MOCK:
            raise ContractValidationError(
                "Local-2 live mode is unavailable; explicit mock mode is required"
            )
        if not isinstance(self.state_path, Path) or not str(self.state_path).strip():
            raise ContractValidationError("Local-2 state_path must be a non-empty Path")
        if not isinstance(self.inventory_path, Path) or not str(
            self.inventory_path
        ).strip():
            raise ContractValidationError(
                "Local-2 inventory_path must be a non-empty Path"
            )
        if self.state_path == self.inventory_path:
            raise ContractValidationError(
                "Local-2 durable truth and mock inventory paths must be separate"
            )
        if (
            isinstance(self.request_ttl_seconds, bool)
            or not isinstance(self.request_ttl_seconds, int)
            or not 60 <= self.request_ttl_seconds <= 3_600
        ):
            raise ContractValidationError(
                "Local-2 request TTL must be between 60 and 3600 seconds"
            )

    @classmethod
    def from_environment(cls) -> "LocalHitlSettings":
        """Load local-only paths and TTL without discovering cloud credentials."""

        raw_mode = os.getenv("AIOA_LOCAL_MODE", LocalFirstMode.MOCK.value)
        try:
            mode = LocalFirstMode(raw_mode)
        except ValueError as error:
            raise ContractValidationError("AIOA_LOCAL_MODE must be mock or live") from error
        raw_state = os.getenv(
            "AIOA_LOCAL_HITL_STATE_PATH",
            ".local/aioa-local-hitl-state.json",
        )
        raw_inventory = os.getenv(
            "AIOA_LOCAL_INVENTORY_PATH",
            ".local/aioa-local-mock-inventory.json",
        )
        raw_ttl = os.getenv("AIOA_LOCAL_APPROVAL_TTL_SECONDS", "600")
        try:
            ttl = int(raw_ttl)
        except ValueError as error:
            raise ContractValidationError(
                "AIOA_LOCAL_APPROVAL_TTL_SECONDS must be an integer"
            ) from error
        return cls(
            mode=mode,
            state_path=Path(raw_state),
            inventory_path=Path(raw_inventory),
            request_ttl_seconds=ttl,
        )

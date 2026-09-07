"""Server-side OpenRouter configuration for the bounded Strands provider."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Final

from aioa_cloudops_agent.domain.errors import ContractValidationError

DEFAULT_OPENROUTER_BASE_URL: Final = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_MODEL: Final = "openai/gpt-4o-mini"
DEFAULT_OPENROUTER_MAX_OUTPUT_TOKENS: Final = 1_024
DEFAULT_OPENROUTER_TIMEOUT_SECONDS: Final = 30

_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}/[A-Za-z0-9][A-Za-z0-9._:-]{0,159}")


def _positive_integer(name: str, default: int, *, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as error:
        raise ContractValidationError(f"{name} must be an integer") from error
    if isinstance(value, bool) or not 1 <= value <= maximum:
        raise ContractValidationError(f"{name} must be between 1 and {maximum}")
    return value


@dataclass(frozen=True, slots=True)
class OpenRouterSettings:
    """Validated OpenRouter endpoint and secret; repr deliberately omits the key."""

    api_key: str = field(repr=False)
    model_id: str = DEFAULT_OPENROUTER_MODEL
    base_url: str = DEFAULT_OPENROUTER_BASE_URL
    max_output_tokens: int = DEFAULT_OPENROUTER_MAX_OUTPUT_TOKENS
    timeout_seconds: int = DEFAULT_OPENROUTER_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if (
            not isinstance(self.api_key, str)
            or not self.api_key
            or self.api_key != self.api_key.strip()
            or any(character.isspace() for character in self.api_key)
            or len(self.api_key) > 512
        ):
            raise ContractValidationError("OPENROUTER_API_KEY is missing or invalid")
        if not isinstance(self.model_id, str) or _MODEL_ID.fullmatch(self.model_id) is None:
            raise ContractValidationError("OPENROUTER_MODEL is invalid")
        if self.base_url.rstrip("/") != DEFAULT_OPENROUTER_BASE_URL:
            raise ContractValidationError(
                "OPENROUTER_BASE_URL must be the canonical OpenRouter API endpoint"
            )
        if (
            isinstance(self.max_output_tokens, bool)
            or not isinstance(self.max_output_tokens, int)
            or not 1 <= self.max_output_tokens <= 8_192
        ):
            raise ContractValidationError(
                "OPENROUTER_MAX_OUTPUT_TOKENS must be between 1 and 8192"
            )
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, int)
            or not 1 <= self.timeout_seconds <= 120
        ):
            raise ContractValidationError(
                "AIOA_PROVIDER_TIMEOUT_SECONDS must be between 1 and 120"
            )

    @classmethod
    def from_environment(cls) -> OpenRouterSettings:
        """Load the selected live provider without inspecting any other credentials."""

        key = os.getenv("OPENROUTER_API_KEY")
        if key is None:
            raise ContractValidationError(
                "OPENROUTER_API_KEY is required when OpenRouter is selected"
            )
        return cls(
            api_key=key,
            model_id=os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL),
            base_url=os.getenv(
                "OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL
            ).rstrip("/"),
            max_output_tokens=_positive_integer(
                "OPENROUTER_MAX_OUTPUT_TOKENS",
                DEFAULT_OPENROUTER_MAX_OUTPUT_TOKENS,
                maximum=8_192,
            ),
            timeout_seconds=_positive_integer(
                "AIOA_PROVIDER_TIMEOUT_SECONDS",
                DEFAULT_OPENROUTER_TIMEOUT_SECONDS,
                maximum=120,
            ),
        )

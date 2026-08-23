"""Fail-closed configuration for the single Strands and Bedrock runtime."""

import os
from dataclasses import dataclass
from typing import Final

from aioa_cloudops_agent.domain.errors import ContractValidationError

from .settings import DEFAULT_AWS_REGION, DEFAULT_MODEL_MAX_OUTPUT_TOKENS

DEFAULT_BEDROCK_MODEL_ID: Final = "eu.amazon.nova-2-lite-v1:0"
DEFAULT_BEDROCK_REGION: Final = DEFAULT_AWS_REGION
DEFAULT_MODEL_TEMPERATURE: Final = 0.0


def _read_positive_integer(name: str, value: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ContractValidationError(f"{name} must be a positive integer") from error
    if parsed <= 0:
        raise ContractValidationError(f"{name} must be a positive integer")
    return parsed


@dataclass(frozen=True, slots=True)
class BedrockSettings:
    """Explicit Bedrock provider settings without a fallback model."""

    model_id: str = DEFAULT_BEDROCK_MODEL_ID
    region: str = DEFAULT_BEDROCK_REGION
    max_output_tokens: int = DEFAULT_MODEL_MAX_OUTPUT_TOKENS
    temperature: float = DEFAULT_MODEL_TEMPERATURE

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ContractValidationError("Bedrock model_id must be a non-empty string")
        if self.model_id != self.model_id.strip():
            raise ContractValidationError("Bedrock model_id must not contain surrounding whitespace")
        if not isinstance(self.region, str) or self.region != DEFAULT_BEDROCK_REGION:
            raise ContractValidationError(f"Bedrock region must be {DEFAULT_BEDROCK_REGION}")
        if (
            isinstance(self.max_output_tokens, bool)
            or not isinstance(self.max_output_tokens, int)
            or self.max_output_tokens <= 0
            or self.max_output_tokens > DEFAULT_MODEL_MAX_OUTPUT_TOKENS
        ):
            raise ContractValidationError(
                f"Bedrock max_output_tokens must be between 1 and {DEFAULT_MODEL_MAX_OUTPUT_TOKENS}"
            )
        if isinstance(self.temperature, bool) or not isinstance(
            self.temperature, (int, float)
        ):
            raise ContractValidationError("Bedrock temperature must be numeric")
        if float(self.temperature) != DEFAULT_MODEL_TEMPERATURE:
            raise ContractValidationError("Bedrock temperature must be 0")

    @classmethod
    def from_environment(cls) -> "BedrockSettings":
        """Load non-secret provider settings with explicit validation."""

        return cls(
            model_id=os.getenv("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID),
            region=os.getenv("BEDROCK_REGION", DEFAULT_BEDROCK_REGION),
            max_output_tokens=_read_positive_integer(
                "MODEL_MAX_OUTPUT_TOKENS",
                os.getenv(
                    "MODEL_MAX_OUTPUT_TOKENS",
                    str(DEFAULT_MODEL_MAX_OUTPUT_TOKENS),
                ),
            ),
            temperature=DEFAULT_MODEL_TEMPERATURE,
        )

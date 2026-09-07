"""Top-level runtime selection with an explicit portable default."""

import os
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Final

from aioa_cloudops_agent.domain.errors import ContractValidationError

from .agent import BedrockSettings
from .openrouter import OpenRouterSettings

PORTABLE_MODEL_ID: Final = "aioa.mock.deterministic-v1"


class RuntimeMode(StrEnum):
    """Closed application runtime modes; cloud use is never inferred."""

    PORTABLE = "portable"
    AWS = "aws"


class ModelProviderName(StrEnum):
    """Providers supported by the current single Strands-agent runtime."""

    MOCK = "mock"
    OPENROUTER = "openrouter"
    BEDROCK = "bedrock"


def _parse_aws_opt_in(value: str) -> bool:
    normalized = value.casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ContractValidationError(
        "AIOA_AWS_INTEGRATION_ENABLED must be exactly true or false"
    )


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    """Explicit provider selection plus server-side provider settings."""

    mode: RuntimeMode = RuntimeMode.PORTABLE
    model_provider: ModelProviderName = ModelProviderName.MOCK
    aws_integration_enabled: bool = False
    bedrock: BedrockSettings | None = None
    openrouter: OpenRouterSettings | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, RuntimeMode):
            raise ContractValidationError("runtime mode must be portable or aws")
        if not isinstance(self.model_provider, ModelProviderName):
            raise ContractValidationError(
                "model provider must be mock, openrouter, or bedrock"
            )
        if not isinstance(self.aws_integration_enabled, bool):
            raise ContractValidationError("AWS integration opt-in must be a boolean")
        if self.mode is RuntimeMode.PORTABLE:
            if self.model_provider not in {
                ModelProviderName.MOCK,
                ModelProviderName.OPENROUTER,
            }:
                raise ContractValidationError(
                    "portable runtime supports only mock or OpenRouter"
                )
            if self.aws_integration_enabled or self.bedrock is not None:
                raise ContractValidationError(
                    "portable runtime forbids AWS integration configuration"
                )
            if (
                self.model_provider is ModelProviderName.OPENROUTER
                and not isinstance(self.openrouter, OpenRouterSettings)
            ):
                raise ContractValidationError(
                    "OpenRouter runtime requires server-side OpenRouter configuration"
                )
            return
        if self.model_provider is not ModelProviderName.BEDROCK:
            raise ContractValidationError("AWS runtime requires the explicit bedrock provider")
        if not self.aws_integration_enabled:
            raise ContractValidationError(
                "AWS runtime requires AIOA_AWS_INTEGRATION_ENABLED=true"
            )
        if not isinstance(self.bedrock, BedrockSettings):
            raise ContractValidationError(
                "AWS runtime requires explicit Bedrock model and region configuration"
            )
        if self.openrouter is not None:
            raise ContractValidationError("AWS runtime forbids OpenRouter configuration")

    @property
    def aws_calls_allowed(self) -> bool:
        """Return the explicit AWS provider boundary, never credential availability."""

        return self.mode is RuntimeMode.AWS and self.aws_integration_enabled

    @property
    def external_network_allowed(self) -> bool:
        """Return true only for the explicitly selected remote provider."""

        return self.model_provider in {
            ModelProviderName.OPENROUTER,
            ModelProviderName.BEDROCK,
        }

    def with_model_provider(self, provider: ModelProviderName) -> "RuntimeSettings":
        """Select a configured portable provider without changing its authority surface."""

        if self.mode is not RuntimeMode.PORTABLE:
            raise ContractValidationError("provider selection is portable-only")
        if provider not in {ModelProviderName.MOCK, ModelProviderName.OPENROUTER}:
            raise ContractValidationError("portable provider must be mock or openrouter")
        return replace(self, model_provider=provider)

    @classmethod
    def from_environment(cls) -> "RuntimeSettings":
        """Load explicit provider settings without creating clients or discovering AWS credentials."""

        raw_mode = os.getenv("AIOA_RUNTIME_MODE", RuntimeMode.PORTABLE.value)
        raw_provider = os.getenv("AIOA_MODEL_PROVIDER", ModelProviderName.MOCK.value)
        try:
            mode = RuntimeMode(raw_mode)
        except ValueError as error:
            raise ContractValidationError(
                "AIOA_RUNTIME_MODE must be portable or aws"
            ) from error
        try:
            provider = ModelProviderName(raw_provider)
        except ValueError as error:
            raise ContractValidationError(
                "AIOA_MODEL_PROVIDER must be mock, openrouter, or bedrock"
            ) from error
        aws_enabled = _parse_aws_opt_in(
            os.getenv("AIOA_AWS_INTEGRATION_ENABLED", "false")
        )
        bedrock: BedrockSettings | None = None
        openrouter: OpenRouterSettings | None = None
        if mode is RuntimeMode.AWS and provider is ModelProviderName.BEDROCK and aws_enabled:
            if "BEDROCK_MODEL_ID" not in os.environ or "BEDROCK_REGION" not in os.environ:
                raise ContractValidationError(
                    "AWS runtime requires explicit Bedrock model and region configuration"
                )
            bedrock = BedrockSettings.from_environment()
        if mode is RuntimeMode.PORTABLE and (
            provider is ModelProviderName.OPENROUTER
            or "OPENROUTER_API_KEY" in os.environ
        ):
            openrouter = OpenRouterSettings.from_environment()
        return cls(
            mode=mode,
            model_provider=provider,
            aws_integration_enabled=aws_enabled,
            bedrock=bedrock,
            openrouter=openrouter,
        )

"""OpenRouter through the OpenAI-compatible Strands model adapter."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, NoReturn

import openai
from strands.models.openai import OpenAIModel
from strands.types.exceptions import ModelThrottledException

from aioa_cloudops_agent.config.openrouter import OpenRouterSettings

from .model import (
    ModelProviderNonRetryableError,
    ModelProviderRetryableError,
    ModelProviderTimeoutError,
    ModelProviderUnavailableError,
)


class OpenRouterModelProvider(OpenAIModel):
    """Count and normalize the one explicitly allowlisted remote provider."""

    def __init__(self, settings: OpenRouterSettings) -> None:
        if not isinstance(settings, OpenRouterSettings):
            raise TypeError("settings must be OpenRouterSettings")
        self.calls = 0
        self.network_calls = 0
        super().__init__(
            client_args={
                "api_key": settings.api_key,
                "base_url": settings.base_url,
                "max_retries": 0,
                "timeout": float(settings.timeout_seconds),
            },
            model_id=settings.model_id,
            params={"max_tokens": settings.max_output_tokens},
            stream=False,
        )

    async def stream(self, *args: Any, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
        self.calls += 1
        self.network_calls += 1
        try:
            async for event in super().stream(*args, **kwargs):
                yield event
        except (openai.APITimeoutError, TimeoutError):
            raise ModelProviderTimeoutError("OpenRouter request timed out") from None
        except (openai.RateLimitError, ModelThrottledException):
            raise ModelProviderRetryableError("OpenRouter rate limit reached") from None
        except openai.AuthenticationError:
            raise ModelProviderNonRetryableError(
                "OpenRouter authentication failed"
            ) from None
        except openai.APIConnectionError:
            raise ModelProviderUnavailableError("OpenRouter is unavailable") from None
        except openai.APIStatusError as error:
            self._raise_status(error)
        except (KeyError, TypeError, ValueError):
            raise ModelProviderNonRetryableError(
                "OpenRouter returned an invalid response"
            ) from None

    @staticmethod
    def _raise_status(error: openai.APIStatusError) -> NoReturn:
        status = error.status_code
        if status == 429 or status >= 500:
            raise ModelProviderRetryableError(
                "OpenRouter request failed transiently"
            ) from None
        raise ModelProviderNonRetryableError("OpenRouter request was rejected") from None

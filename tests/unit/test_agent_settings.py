import pytest

from aioa_cloudops_agent.config import BedrockSettings
from aioa_cloudops_agent.domain import ContractValidationError


def test_bedrock_settings_use_explicit_nova_candidate_defaults() -> None:
    settings = BedrockSettings()

    assert settings.model_id == "eu.amazon.nova-2-lite-v1:0"
    assert settings.region == "eu-central-1"
    assert settings.max_output_tokens == 1_024
    assert settings.temperature == 0


def test_bedrock_settings_are_environment_configurable_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BEDROCK_MODEL_ID", "eu.amazon.nova-2-lite-v1:0")
    monkeypatch.setenv("BEDROCK_REGION", "eu-central-1")
    monkeypatch.setenv("MODEL_MAX_OUTPUT_TOKENS", "256")

    settings = BedrockSettings.from_environment()

    assert settings.model_id == "eu.amazon.nova-2-lite-v1:0"
    assert settings.max_output_tokens == 256


@pytest.mark.parametrize(
    "overrides",
    [
        {"model_id": ""},
        {"model_id": " anthropic.claude-3-haiku-20240307-v1:0"},
        {"region": "us-east-1"},
        {"max_output_tokens": 0},
        {"max_output_tokens": 1_025},
        {"max_output_tokens": True},
        {"temperature": 0.1},
        {"temperature": True},
    ],
)
def test_invalid_bedrock_settings_fail_explicitly(overrides: dict[str, object]) -> None:
    with pytest.raises(ContractValidationError):
        BedrockSettings(**overrides)


def test_malformed_environment_token_cap_fails_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_MAX_OUTPUT_TOKENS", "not-an-integer")

    with pytest.raises(ContractValidationError, match="positive integer"):
        BedrockSettings.from_environment()


def test_no_claude_haiku_fallback_is_encoded() -> None:
    settings = BedrockSettings()

    assert "claude" not in settings.model_id.casefold()
    assert "haiku" not in settings.model_id.casefold()

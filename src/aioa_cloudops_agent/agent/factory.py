"""Factory for exactly one Strands Agent subordinate to Non-Zero authority."""

from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from opentelemetry.trace import Tracer
from strands import Agent
from strands.models import BedrockModel, Model
from strands.tools.decorator import DecoratedFunctionTool
from strands.vended_interventions.hitl import HumanInTheLoop

from aioa_cloudops_agent.cloudops import (
    INSPECT_INSTANCE_TOOL_NAME,
    Ec2DescribeInstancesClient,
    InspectInstanceService,
    SandboxTarget,
    create_inspect_instance_tool,
)
from aioa_cloudops_agent.config import BedrockSettings
from aioa_cloudops_agent.domain import AuthorityGate, ContractValidationError, ExecutionContext

from .prompts import SYSTEM_PROMPT
from .tracing import PRIMARY_AGENT_ID, build_agent_trace_attributes

PRIMARY_AGENT_COUNT: Final = 1
CURRENT_REGISTERED_TOOL_COUNT: Final = 1
FINAL_TOOL_CAP: Final = 5


@dataclass(frozen=True, slots=True)
class PrimaryAgentRuntime:
    """References required to invoke and audit the one primary agent."""

    agent: Agent
    inspect_instance_tool: DecoratedFunctionTool
    human_in_the_loop: HumanInTheLoop
    correlation_id: UUID
    model_settings: BedrockSettings
    target: SandboxTarget

    @property
    def registered_tool_names(self) -> tuple[str, ...]:
        """Return the active tool surface without dynamic discovery."""

        return tuple(self.agent.tool_names)


def create_bedrock_model(
    settings: BedrockSettings,
    *,
    boto_session: Any | None = None,
) -> BedrockModel:
    """Create the explicit Nova candidate provider without fallback behavior."""

    if not isinstance(settings, BedrockSettings):
        raise ContractValidationError("settings must be BedrockSettings")
    model_config = {
        "model_id": settings.model_id,
        "temperature": float(settings.temperature),
        "max_tokens": settings.max_output_tokens,
        "streaming": True,
    }
    if boto_session is not None:
        if getattr(boto_session, "region_name", None) != settings.region:
            raise ContractValidationError("boto_session region must match Bedrock settings")
        return BedrockModel(boto_session=boto_session, **model_config)
    return BedrockModel(region_name=settings.region, **model_config)


def create_human_in_the_loop() -> HumanInTheLoop:
    """Allow only inspect_instance without confirmation; all other tools interrupt."""

    return HumanInTheLoop(
        allowed_tools=[INSPECT_INSTANCE_TOOL_NAME],
        classifier=None,
        enable_trust=False,
        ask=None,
    )


def create_primary_agent(
    *,
    context: ExecutionContext,
    target: SandboxTarget,
    ec2_client: Ec2DescribeInstancesClient,
    model_settings: BedrockSettings | None = None,
    model: Model | None = None,
    tracer: Tracer | None = None,
) -> PrimaryAgentRuntime:
    """Create one Strands Agent with one AUTO read-only tool and native HITL."""

    if not isinstance(context, ExecutionContext):
        raise ContractValidationError("context must be an ExecutionContext")
    if context.authority_gate is not AuthorityGate.AUTO:
        raise ContractValidationError("current read-only agent context must use AUTO")
    if not isinstance(target, SandboxTarget):
        raise ContractValidationError("target must be a SandboxTarget")
    settings = model_settings if model_settings is not None else BedrockSettings()
    if not isinstance(settings, BedrockSettings):
        raise ContractValidationError("model_settings must be BedrockSettings")

    inspection_service = InspectInstanceService(
        ec2_client,
        target,
        region=settings.region,
    )
    inspection_tool = create_inspect_instance_tool(
        inspection_service,
        context.correlation_id,
        tracer=tracer,
    )
    intervention = create_human_in_the_loop()
    primary_agent = Agent(
        agent_id=PRIMARY_AGENT_ID,
        name="AIOA Non-Zero CloudOps",
        description="Bounded read-only sandbox EC2 inspection agent",
        model=model if model is not None else create_bedrock_model(settings),
        tools=[inspection_tool],
        interventions=[intervention],
        system_prompt=SYSTEM_PROMPT,
        callback_handler=None,
        load_tools_from_directory=False,
        record_direct_tool_call=True,
        trace_attributes=build_agent_trace_attributes(context.correlation_id),
    )
    if primary_agent.tool_names != [INSPECT_INSTANCE_TOOL_NAME]:
        raise ContractValidationError("primary agent tool surface is not canonical")
    return PrimaryAgentRuntime(
        agent=primary_agent,
        inspect_instance_tool=inspection_tool,
        human_in_the_loop=intervention,
        correlation_id=context.correlation_id,
        model_settings=settings,
        target=target,
    )

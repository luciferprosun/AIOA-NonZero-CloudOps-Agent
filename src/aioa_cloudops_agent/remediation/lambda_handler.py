"""Private Lambda entry point; this module alone constructs the EC2 stop client."""

from datetime import UTC, datetime
from typing import Any

from aioa_cloudops_agent.config import SandboxRemediationSettings

from .emergency import EnvironmentEmergencyExecutionControl, emergency_denial_payload
from .errors import RemediationEmergencyDisabledError
from .executor import Ec2SandboxStopExecutor
from .models import StopExecutionCommand


def lambda_handler(event: object, context: object) -> dict[str, Any]:
    """Validate one command and execute the gated graceful stop with no retries."""

    del context
    import boto3

    settings = SandboxRemediationSettings.from_environment()
    command = StopExecutionCommand.model_validate(event)
    client = boto3.client("ec2", region_name=settings.region)
    try:
        acknowledgement = Ec2SandboxStopExecutor(
            client,
            settings,
            emergency_control=EnvironmentEmergencyExecutionControl(),
            clock=lambda: datetime.now(UTC),
        ).execute(command)
    except RemediationEmergencyDisabledError:
        return emergency_denial_payload()
    return acknowledgement.model_dump(mode="json")

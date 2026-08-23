"""Private Lambda entry point; this module alone constructs the EC2 stop client."""

from datetime import UTC, datetime
from typing import Any

from aioa_cloudops_agent.config import SandboxRemediationSettings

from .executor import Ec2SandboxStopExecutor
from .models import StopExecutionCommand


def lambda_handler(event: object, context: object) -> dict[str, Any]:
    """Validate one command and execute the gated graceful stop with no retries."""

    del context
    import boto3

    settings = SandboxRemediationSettings.from_environment()
    command = StopExecutionCommand.model_validate(event)
    client = boto3.client("ec2", region_name=settings.region)
    acknowledgement = Ec2SandboxStopExecutor(
        client,
        settings,
        clock=lambda: datetime.now(UTC),
    ).execute(command)
    return acknowledgement.model_dump(mode="json")

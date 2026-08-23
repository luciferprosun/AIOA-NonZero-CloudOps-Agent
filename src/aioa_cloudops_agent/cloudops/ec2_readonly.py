"""Narrow protocol for the only currently allowlisted EC2 read operation."""

from collections.abc import Mapping
from typing import Any, Protocol


class Ec2ReadOnlyClient(Protocol):
    """Provider client exposing observation only, with no remediation method."""

    def describe_addresses(self) -> Mapping[str, Any]:
        """Return allocated Elastic IP metadata."""

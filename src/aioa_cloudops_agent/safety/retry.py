"""Explicit bounded retry rules for read-only dependencies only."""

from collections.abc import Callable, Mapping
from enum import StrEnum
from typing import Final, TypeVar


class RetryOperationClass(StrEnum):
    """Closed operation classes used by the automatic retry matrix."""

    MODEL_SCHEMA_CORRECTION = "MODEL_SCHEMA_CORRECTION"
    READ_ONLY_DEPENDENCY = "READ_ONLY_DEPENDENCY"
    READ_ONLY_VALIDATION = "READ_ONLY_VALIDATION"
    DURABLE_CONDITIONAL_CONFLICT = "DURABLE_CONDITIONAL_CONFLICT"
    MUTATION_BEFORE_SEND = "MUTATION_BEFORE_SEND"
    MUTATION_ACK_AMBIGUOUS = "MUTATION_ACK_AMBIGUOUS"
    VERIFICATION_POLL = "VERIFICATION_POLL"


AUTOMATIC_RETRY_ALLOWED: Final[dict[RetryOperationClass, bool]] = {
    RetryOperationClass.MODEL_SCHEMA_CORRECTION: True,
    RetryOperationClass.READ_ONLY_DEPENDENCY: True,
    RetryOperationClass.READ_ONLY_VALIDATION: False,
    RetryOperationClass.DURABLE_CONDITIONAL_CONFLICT: False,
    RetryOperationClass.MUTATION_BEFORE_SEND: False,
    RetryOperationClass.MUTATION_ACK_AMBIGUOUS: False,
    RetryOperationClass.VERIFICATION_POLL: True,
}

_TRANSIENT_CODES: Final[frozenset[str]] = frozenset(
    {
        "InternalError",
        "InternalFailure",
        "RequestTimeout",
        "RequestTimeoutException",
        "ServiceUnavailable",
        "ServiceUnavailableException",
        "Throttling",
        "ThrottlingException",
        "TooManyRequestsException",
    }
)
_TRANSIENT_HTTP_STATUSES: Final[frozenset[int]] = frozenset({429, 500, 502, 503, 504})


def is_known_transient_read_error(error: Exception) -> bool:
    """Recognize only allow-listed transient read failures; AccessDenied is permanent."""

    if isinstance(error, (TimeoutError, ConnectionError)):
        return True
    response = getattr(error, "response", None)
    if not isinstance(response, Mapping):
        return False
    details = response.get("Error")
    code = details.get("Code") if isinstance(details, Mapping) else None
    metadata = response.get("ResponseMetadata")
    status = metadata.get("HTTPStatusCode") if isinstance(metadata, Mapping) else None
    return code in _TRANSIENT_CODES or status in _TRANSIENT_HTTP_STATUSES


ResultValue = TypeVar("ResultValue")


class BoundedReadRetry:
    """Retry a read only for known transient failures and a fixed attempt cap."""

    def __init__(
        self,
        *,
        max_attempts: int = 2,
        sleeper: Callable[[int], None] | None = None,
    ) -> None:
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int):
            raise TypeError("max_attempts must be an integer")
        if not 1 <= max_attempts <= 3:
            raise ValueError("read retry max_attempts must be between 1 and 3")
        if sleeper is not None and not callable(sleeper):
            raise TypeError("sleeper must be callable")
        self._max_attempts = max_attempts
        self._sleeper = sleeper or (lambda _: None)

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    def run(
        self,
        operation: Callable[[], ResultValue],
        *,
        operation_class: RetryOperationClass = RetryOperationClass.READ_ONLY_DEPENDENCY,
    ) -> ResultValue:
        """Run a read; mutation and validation classes can never enter this retry loop."""

        if not callable(operation):
            raise TypeError("operation must be callable")
        if operation_class not in {
            RetryOperationClass.READ_ONLY_DEPENDENCY,
            RetryOperationClass.VERIFICATION_POLL,
        }:
            raise ValueError("automatic retry is restricted to read-only operations")
        for attempt in range(1, self._max_attempts + 1):
            try:
                return operation()
            except Exception as error:
                if attempt >= self._max_attempts or not is_known_transient_read_error(error):
                    raise
                self._sleeper(attempt)
        raise AssertionError("bounded retry loop returned no result")

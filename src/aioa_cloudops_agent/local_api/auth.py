"""Constant-time, header-only authentication for the loopback Local-2 API."""

import hashlib
import hmac
from collections.abc import Mapping

from aioa_cloudops_agent.agent.local_hitl import LocalOperatorPrincipal

from .contracts import LOCAL_API_TOKEN_MAX_LENGTH, LOCAL_API_TOKEN_MIN_LENGTH


class LocalApiTokenAuthorizer:
    """Derive a stable operator session from one local bearer token."""

    def __init__(self, token: str) -> None:
        if (
            not isinstance(token, str)
            or token != token.strip()
            or not LOCAL_API_TOKEN_MIN_LENGTH <= len(token) <= LOCAL_API_TOKEN_MAX_LENGTH
        ):
            raise ValueError("local API token length or shape is invalid")
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        self._token_digest = digest
        self._principal = LocalOperatorPrincipal(
            actor_session_id=f"local-api:{digest.hex()[:32]}"
        )

    def authorize(
        self,
        headers: Mapping[str, object],
    ) -> LocalOperatorPrincipal | None:
        """Accept exactly one well-shaped Bearer value and never retain the candidate."""

        value = headers.get("authorization")
        if not isinstance(value, str) or not value.startswith("Bearer "):
            return None
        candidate = value.removeprefix("Bearer ")
        if (
            candidate != candidate.strip()
            or not LOCAL_API_TOKEN_MIN_LENGTH
            <= len(candidate)
            <= LOCAL_API_TOKEN_MAX_LENGTH
        ):
            return None
        candidate_digest = hashlib.sha256(candidate.encode("utf-8")).digest()
        if not hmac.compare_digest(candidate_digest, self._token_digest):
            return None
        return self._principal

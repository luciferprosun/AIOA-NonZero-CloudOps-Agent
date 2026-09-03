"""Local-only authenticated API for the complete human authorization demo."""

from .application import LocalApiApplication
from .auth import LOCAL_API_SESSION_COOKIE, LocalApiTokenAuthorizer
from .contracts import (
    LOCAL_API_BODY_MAX_BYTES,
    LOCAL_API_HEADER_MAX_COUNT,
    LOCAL_API_HEADER_VALUE_MAX_LENGTH,
    LOCAL_API_MAX_CONCURRENT_REQUESTS,
    LOCAL_API_SOCKET_TIMEOUT_SECONDS,
    LOCAL_API_TOKEN_MAX_LENGTH,
    LOCAL_API_TOKEN_MIN_LENGTH,
    LocalApiErrorCode,
    LocalApiErrorResponse,
    LocalAuditEventView,
    LocalBrowserSessionView,
    LocalCheckpointView,
    LocalEvidenceCategory,
    LocalReadyView,
    LocalResumeRequest,
    LocalRuntimeView,
    LocalRunView,
    LocalStartRunRequest,
)
from .server import create_local_http_server, load_or_create_local_token
from .workspace_hero import WorkspaceHeroFailure, WorkspaceHeroOrchestrator
from .workspace_hero_contracts import (
    WORKSPACE_HERO_RESPONSE_MAX_BYTES,
    WORKSPACE_HERO_SCENARIO_ID,
    WorkspaceHeroDecisionRequest,
    WorkspaceHeroProjection,
    WorkspaceHeroResumeRequest,
    WorkspaceHeroStartRequest,
)

__all__ = [
    "LOCAL_API_BODY_MAX_BYTES",
    "LOCAL_API_HEADER_MAX_COUNT",
    "LOCAL_API_HEADER_VALUE_MAX_LENGTH",
    "LOCAL_API_MAX_CONCURRENT_REQUESTS",
    "LOCAL_API_SESSION_COOKIE",
    "LOCAL_API_SOCKET_TIMEOUT_SECONDS",
    "LOCAL_API_TOKEN_MAX_LENGTH",
    "LOCAL_API_TOKEN_MIN_LENGTH",
    "WORKSPACE_HERO_RESPONSE_MAX_BYTES",
    "WORKSPACE_HERO_SCENARIO_ID",
    "LocalApiApplication",
    "LocalApiErrorCode",
    "LocalApiErrorResponse",
    "LocalApiTokenAuthorizer",
    "LocalAuditEventView",
    "LocalBrowserSessionView",
    "LocalCheckpointView",
    "LocalEvidenceCategory",
    "LocalReadyView",
    "LocalResumeRequest",
    "LocalRunView",
    "LocalRuntimeView",
    "LocalStartRunRequest",
    "WorkspaceHeroDecisionRequest",
    "WorkspaceHeroFailure",
    "WorkspaceHeroOrchestrator",
    "WorkspaceHeroProjection",
    "WorkspaceHeroResumeRequest",
    "WorkspaceHeroStartRequest",
    "create_local_http_server",
    "load_or_create_local_token",
]

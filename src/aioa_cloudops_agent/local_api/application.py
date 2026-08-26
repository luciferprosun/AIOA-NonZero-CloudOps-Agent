"""Loopback-only Local-2 HTTP application with an embedded operator console."""

import base64
import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from pydantic import BaseModel, TypeAdapter, ValidationError

from aioa_cloudops_agent.agent.local_composition import LocalHitlRuntime
from aioa_cloudops_agent.agent.local_hitl import (
    LocalDecisionRequest,
    LocalOperatorPrincipal,
)
from aioa_cloudops_agent.nz import (
    BudgetCounters,
    FailureDetail,
    FailureKind,
    ResultStatus,
    Run,
    Uuid7Identifier,
    generate_run_id,
    generate_trace_id,
)
from aioa_cloudops_agent.nz.errors import StorageDependencyError

from .auth import LocalApiTokenAuthorizer
from .contracts import (
    LOCAL_API_BODY_MAX_BYTES,
    LocalApiErrorCode,
    LocalApiErrorResponse,
    LocalResumeRequest,
    LocalRunView,
    LocalStartRunRequest,
)

_RUN_PATH = re.compile(r"^/api/runs/([^/]+)$")
_APPROVAL_PATH = re.compile(r"^/api/runs/([^/]+)/approval-request$")
_DECISION_PATH = re.compile(r"^/api/runs/([^/]+)/decision$")
_RESUME_PATH = re.compile(r"^/api/runs/([^/]+)/resume$")
_UUID7_ADAPTER = TypeAdapter(Uuid7Identifier)
_JSON_HEADERS: Final[dict[str, str]] = {
    "cache-control": "no-store",
    "content-security-policy": "default-src 'none';base-uri 'none';frame-ancestors 'none'",
    "content-type": "application/json",
    "permissions-policy": "camera=(),geolocation=(),microphone=()",
    "referrer-policy": "no-referrer",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
}
_UI_STYLE: Final = """
:root{color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,sans-serif;background:#071018;color:#eaf6f4}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top left,#12353b 0,#071018 42%);min-height:100vh}main{width:min(1080px,calc(100% - 32px));margin:auto;padding:44px 0 64px}.eyebrow{color:#68e1cb;text-transform:uppercase;letter-spacing:.14em;font-weight:700;font-size:.78rem}h1{font-size:clamp(2rem,5vw,4.2rem);line-height:1;margin:.2em 0}.lead{max-width:720px;color:#abc7c3;font-size:1.08rem}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:16px;margin-top:28px}.card{background:#0c1923e6;border:1px solid #24404a;border-radius:18px;padding:20px;box-shadow:0 18px 50px #0006}.card h2{margin-top:0;font-size:1rem;color:#d9fffa}label{display:block;color:#abc7c3;margin:12px 0 6px}input,select,button{width:100%;font:inherit;border-radius:10px;padding:11px 12px}input,select{background:#071018;color:#eaf6f4;border:1px solid #36535c}button{margin-top:10px;border:0;background:#68e1cb;color:#06211d;font-weight:800;cursor:pointer}button.secondary{background:#1d333b;color:#d9fffa}button.danger{background:#ff927e;color:#32100b}button:disabled{opacity:.45;cursor:not-allowed}.actions{display:grid;grid-template-columns:1fr 1fr;gap:9px}.status{display:inline-block;padding:6px 10px;border-radius:999px;background:#18343b;color:#8ff2df;font-weight:700}pre{white-space:pre-wrap;overflow-wrap:anywhere;min-height:330px;max-height:560px;overflow:auto;background:#040a0f;border-radius:12px;padding:14px;color:#bce9e2;font-size:.82rem}.note{font-size:.85rem;color:#8ba9a5}.wide{grid-column:1/-1}
""".strip()
_UI_SCRIPT: Final = """
(()=>{let token='',runId='',challenge=null;const $=id=>document.getElementById(id);const out=$('output'),state=$('state');function show(v){out.textContent=JSON.stringify(v,null,2);const s=v?.result?.run?.state||v?.result?.final_state;state.textContent=s||'READY'}async function api(path,method='GET',body=null){if(!token)throw new Error('Connect with the local token first.');const options={method,headers:{Authorization:'Bearer '+token}};if(body!==null){options.headers['Content-Type']='application/json';options.body=JSON.stringify(body)}const response=await fetch(path,options);const value=await response.json();show(value);if(!response.ok)throw new Error(value.failure_code||value.error||'Request failed');return value.result}$('connect').addEventListener('click',()=>{const input=$('token');token=input.value;input.value='';state.textContent=token?'CONNECTED':'TOKEN REQUIRED'});$('disconnect').addEventListener('click',()=>{token='';runId='';challenge=null;state.textContent='DISCONNECTED';out.textContent='Session cleared from memory.'});$('start').addEventListener('click',async()=>{try{const [resource_type,resource_id]=$('fixture').value.split('|');const result=await api('/api/runs','POST',{resource_type,resource_id});runId=result.run_id;challenge=null}catch(error){out.textContent+='\n'+error.message}});$('statusBtn').addEventListener('click',async()=>{try{if(!runId)throw new Error('Start a run first.');await api('/api/runs/'+runId)}catch(error){out.textContent+='\n'+error.message}});$('challengeBtn').addEventListener('click',async()=>{try{if(!runId)throw new Error('Start a run first.');challenge=await api('/api/runs/'+runId+'/approval-request','POST',{})}catch(error){out.textContent+='\n'+error.message}});async function decide(decision){try{if(!challenge)throw new Error('Request the exact approval challenge first.');const r=challenge.request;await api('/api/runs/'+runId+'/decision','POST',{request_id:r.request_id,run_id:r.run_id,proposal_id:r.proposal_id,request_hash:r.request_hash,proposal_hash:r.proposal_hash,evidence_hash:r.evidence_hash,proposal_version:r.proposal_version,decision,decision_nonce:challenge.decision_nonce})}catch(error){out.textContent+='\n'+error.message}}$('approve').addEventListener('click',()=>decide('APPROVED'));$('deny').addEventListener('click',()=>decide('DENIED'));$('resume').addEventListener('click',async()=>{try{if(!runId)throw new Error('Start a run first.');await api('/api/runs/'+runId+'/resume','POST',{confirm_execution:true})}catch(error){out.textContent+='\n'+error.message}})})();
""".strip()
_UI_STYLE_HASH = base64.b64encode(hashlib.sha256(_UI_STYLE.encode()).digest()).decode()
_UI_SCRIPT_HASH = base64.b64encode(hashlib.sha256(_UI_SCRIPT.encode()).digest()).decode()
_UI_HEADERS: Final[dict[str, str]] = {
    **_JSON_HEADERS,
    "content-security-policy": (
        "default-src 'none';base-uri 'none';connect-src 'self';frame-ancestors 'none';"
        "form-action 'self';"
        f"style-src 'sha256-{_UI_STYLE_HASH}';script-src 'sha256-{_UI_SCRIPT_HASH}'"
    ),
    "content-type": "text/html; charset=utf-8",
}
_UI_BODY: Final = (
    "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>AIOA Agents for Humans — Local HITL</title><style>"
    + _UI_STYLE
    + "</style></head><body><main><div class='eyebrow'>AIOA · Agents for Humans</div>"
    "<h1>Human authority,<br>machine precision.</h1>"
    "<p class='lead'>Inspect a deterministic AWS-shaped fixture, review the exact "
    "evidence-bound remediation, approve or deny it, then verify one protected local change.</p>"
    "<span id='state' class='status'>READY</span><section class='grid'>"
    "<div class='card'><h2>1 · Local session</h2><label for='token'>Bearer token</label>"
    "<input id='token' type='password' autocomplete='off' spellcheck='false'>"
    "<button id='connect'>Connect</button><button id='disconnect' class='secondary'>Clear session</button>"
    "<p class='note'>Loaded only into page memory; never stored by the browser.</p></div>"
    "<div class='card'><h2>2 · Investigate</h2><label for='fixture'>Safe fixture</label>"
    "<select id='fixture'><option value='AWS::EC2::EIP|eipalloc-0123456789abcdef0'>"
    "Unattached Elastic IP</option><option value='AWS::EC2::SecurityGroup|sg-0123456789abcdef0'>"
    "Public SSH ingress</option><option value='AWS::EC2::Instance|i-0fedcba9876543210'>"
    "Missing required tags</option><option value='AWS::EC2::Instance|i-0123456789abcdef0'>"
    "Clean instance</option></select><button id='start'>Start bounded run</button>"
    "<button id='statusBtn' class='secondary'>Refresh durable state</button></div>"
    "<div class='card'><h2>3 · Human decision</h2><button id='challengeBtn'>Review exact proposal</button>"
    "<div class='actions'><button id='approve'>Approve</button><button id='deny' class='danger'>Deny</button></div>"
    "<button id='resume' class='secondary'>Resume protected execution</button>"
    "<p class='note'>Approval and execution are separate, durable transitions.</p></div>"
    "<div class='card wide'><h2>Durable evidence</h2><pre id='output' aria-live='polite'>"
    "Connect, choose a fixture, and start a run.</pre></div></section><script>"
    + _UI_SCRIPT
    + "</script></main></body></html>"
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class _Request:
    method: str
    path: str
    headers: Mapping[str, object]
    body: str | None
    query: str


class _Rejected(ValueError):
    def __init__(self, code: LocalApiErrorCode, status: int) -> None:
        super().__init__(code.value)
        self.code = code
        self.status = status


def _response(
    status: int,
    body: object,
    *,
    headers: Mapping[str, str] = _JSON_HEADERS,
) -> dict[str, object]:
    if isinstance(body, BaseModel):
        body = body.model_dump(mode="json", exclude_none=True)
    rendered = body if isinstance(body, str) else json.dumps(
        body,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return {
        "statusCode": status,
        "headers": dict(headers),
        "body": rendered,
    }


def _ok(status: int, value: BaseModel) -> dict[str, object]:
    return _response(
        status,
        {"ok": True, "result": value.model_dump(mode="json", exclude_none=True)},
    )


def _headers(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise _Rejected(LocalApiErrorCode.BAD_REQUEST, 400)
    normalized: dict[str, object] = {}
    for raw_name, header_value in value.items():
        if not isinstance(raw_name, str) or not raw_name or raw_name != raw_name.strip():
            raise _Rejected(LocalApiErrorCode.BAD_REQUEST, 400)
        name = raw_name.casefold()
        if name in normalized:
            raise _Rejected(LocalApiErrorCode.BAD_REQUEST, 400)
        normalized[name] = header_value
    return normalized


def _parse_request(event: object) -> _Request:
    if not isinstance(event, Mapping):
        raise _Rejected(LocalApiErrorCode.BAD_REQUEST, 400)
    method = event.get("method")
    path = event.get("path")
    query = event.get("query", "")
    body = event.get("body")
    if (
        not isinstance(method, str)
        or re.fullmatch(r"[A-Z]{3,16}", method) is None
        or not isinstance(path, str)
        or not path.startswith("/")
        or len(path) > 256
        or not isinstance(query, str)
        or (body is not None and not isinstance(body, str))
    ):
        raise _Rejected(LocalApiErrorCode.BAD_REQUEST, 400)
    if body is not None:
        try:
            body_size = len(body.encode("utf-8"))
        except UnicodeError as error:
            raise _Rejected(LocalApiErrorCode.BAD_REQUEST, 400) from error
        if body_size > LOCAL_API_BODY_MAX_BYTES:
            raise _Rejected(LocalApiErrorCode.PAYLOAD_TOO_LARGE, 413)
    return _Request(
        method=method,
        path=path,
        headers=_headers(event.get("headers")),
        body=body,
        query=query,
    )


def _strict_json(value: str) -> object:
    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for name, item in values:
            if name in result:
                raise ValueError("duplicate JSON key")
            result[name] = item
        return result

    def reject_constant(_value: str) -> None:
        raise ValueError("non-finite JSON value")

    return json.loads(value, object_pairs_hook=pairs, parse_constant=reject_constant)


def _json_model[Model: BaseModel](request: _Request, model: type[Model]) -> Model:
    if request.query:
        raise _Rejected(LocalApiErrorCode.BAD_REQUEST, 400)
    if request.headers.get("content-type") != "application/json":
        raise _Rejected(LocalApiErrorCode.UNSUPPORTED_MEDIA_TYPE, 415)
    if request.body is None:
        raise _Rejected(LocalApiErrorCode.BAD_REQUEST, 400)
    try:
        return model.model_validate(_strict_json(request.body))
    except (RecursionError, TypeError, ValueError, ValidationError) as error:
        raise _Rejected(LocalApiErrorCode.BAD_REQUEST, 400) from error


class LocalApiApplication:
    """Expose public liveness/UI and authenticated Local-2 workflow endpoints."""

    def __init__(
        self,
        runtime: LocalHitlRuntime,
        authorizer: LocalApiTokenAuthorizer,
        *,
        clock: Callable[[], datetime] = _utc_now,
        run_id_factory: Callable[[], UUID] = generate_run_id,
        trace_id_factory: Callable[[], UUID] = generate_trace_id,
    ) -> None:
        if not isinstance(runtime, LocalHitlRuntime):
            raise TypeError("runtime must be LocalHitlRuntime")
        if not isinstance(authorizer, LocalApiTokenAuthorizer):
            raise TypeError("authorizer must be LocalApiTokenAuthorizer")
        if not all(callable(value) for value in (clock, run_id_factory, trace_id_factory)):
            raise TypeError("clock and identifier factories must be callable")
        self._runtime = runtime
        self._authorizer = authorizer
        self._clock = clock
        self._run_id_factory = run_id_factory
        self._trace_id_factory = trace_id_factory

    def handle(self, event: object) -> dict[str, object]:
        try:
            request = _parse_request(event)
        except _Rejected as rejection:
            return self._error(rejection.code, rejection.status)

        if request.path == "/health":
            return self._public_get(
                request,
                _response(200, {"mode": "mock", "service": "aioa-local-hitl", "status": "ok"}),
            )
        if request.path == "/":
            return self._public_get(
                request,
                _response(200, _UI_BODY, headers=_UI_HEADERS),
            )
        if request.path == "/api/runs":
            return self._start(request)
        for pattern, handler in (
            (_APPROVAL_PATH, self._approval_request),
            (_DECISION_PATH, self._decision),
            (_RESUME_PATH, self._resume),
            (_RUN_PATH, self._status),
        ):
            match = pattern.fullmatch(request.path)
            if match is not None:
                return handler(request, match.group(1))
        return self._error(LocalApiErrorCode.NOT_FOUND, 404)

    def _public_get(
        self,
        request: _Request,
        response: dict[str, object],
    ) -> dict[str, object]:
        if request.method != "GET":
            return self._error(LocalApiErrorCode.METHOD_NOT_ALLOWED, 405)
        if request.query or request.body not in (None, ""):
            return self._error(LocalApiErrorCode.BAD_REQUEST, 400)
        return response

    def _principal(self, request: _Request) -> LocalOperatorPrincipal | None:
        try:
            return self._authorizer.authorize(request.headers)
        except Exception:
            return None

    def _protected(
        self,
        request: _Request,
        *,
        method: str,
    ) -> LocalOperatorPrincipal | dict[str, object]:
        if request.method != method:
            return self._error(LocalApiErrorCode.METHOD_NOT_ALLOWED, 405)
        principal = self._principal(request)
        if principal is None:
            return self._error(LocalApiErrorCode.UNAUTHORIZED, 401)
        return principal

    def _start(self, request: _Request) -> dict[str, object]:
        protected = self._protected(request, method="POST")
        if isinstance(protected, dict):
            return protected
        try:
            start = _json_model(request, LocalStartRunRequest)
            now = self._clock()
            run_id = self._run_id_factory()
            run = Run.new(
                run_id=run_id,
                trace_id=self._trace_id_factory(),
                correlation_id=self._trace_id_factory(),
                idempotency_key=f"local/api/{run_id}",
                created_at=now,
                budget=BudgetCounters(
                    max_turns=8,
                    max_tokens=2_048,
                    max_elapsed_seconds=60,
                ),
            )
            result = self._runtime.phase_one.execute(run, start.to_query())
        except _Rejected as rejection:
            return self._error(rejection.code, rejection.status)
        except Exception:
            return self._error(LocalApiErrorCode.INTERNAL_ERROR, 500)
        if result.status is ResultStatus.FAILURE or result.value is None:
            return self._flow_failure(result.failure)
        return _ok(201, result.value)

    def _status(self, request: _Request, raw_run_id: str) -> dict[str, object]:
        protected = self._protected(request, method="GET")
        if isinstance(protected, dict):
            return protected
        if request.query or request.body not in (None, ""):
            return self._error(LocalApiErrorCode.BAD_REQUEST, 400)
        run_id = self._run_id(raw_run_id)
        if run_id is None:
            return self._error(LocalApiErrorCode.BAD_REQUEST, 400)
        try:
            run = self._runtime.repository.get_run(run_id)
            checkpoint = self._runtime.repository.get_checkpoint(run_id)
        except (StorageDependencyError, TypeError, ValueError):
            return self._error(LocalApiErrorCode.DEPENDENCY_UNAVAILABLE, 503, retryable=True)
        if run is None:
            return self._error(LocalApiErrorCode.NOT_FOUND, 404)
        return _ok(200, LocalRunView(run=run, checkpoint=checkpoint))

    def _approval_request(
        self,
        request: _Request,
        raw_run_id: str,
    ) -> dict[str, object]:
        protected = self._protected(request, method="POST")
        if isinstance(protected, dict):
            return protected
        run_id = self._run_id(raw_run_id)
        if run_id is None:
            return self._error(LocalApiErrorCode.BAD_REQUEST, 400)
        try:
            _json_model(request, _EmptyRequest)
            result = self._runtime.phase_two.request_approval(run_id, protected)
        except _Rejected as rejection:
            return self._error(rejection.code, rejection.status)
        except Exception:
            return self._error(LocalApiErrorCode.INTERNAL_ERROR, 500)
        if result.status is ResultStatus.FAILURE or result.value is None:
            return self._flow_failure(result.failure)
        return _ok(200, result.value)

    def _decision(self, request: _Request, raw_run_id: str) -> dict[str, object]:
        protected = self._protected(request, method="POST")
        if isinstance(protected, dict):
            return protected
        run_id = self._run_id(raw_run_id)
        if run_id is None:
            return self._error(LocalApiErrorCode.BAD_REQUEST, 400)
        try:
            decision = _json_model(request, LocalDecisionRequest)
            if decision.run_id != run_id:
                raise _Rejected(LocalApiErrorCode.BAD_REQUEST, 400)
            result = self._runtime.phase_two.decide(decision, protected)
        except _Rejected as rejection:
            return self._error(rejection.code, rejection.status)
        except Exception:
            return self._error(LocalApiErrorCode.INTERNAL_ERROR, 500)
        if result.status is ResultStatus.FAILURE or result.value is None:
            return self._flow_failure(result.failure)
        return _ok(200, result.value)

    def _resume(self, request: _Request, raw_run_id: str) -> dict[str, object]:
        protected = self._protected(request, method="POST")
        if isinstance(protected, dict):
            return protected
        run_id = self._run_id(raw_run_id)
        if run_id is None:
            return self._error(LocalApiErrorCode.BAD_REQUEST, 400)
        try:
            _json_model(request, LocalResumeRequest)
            result = self._runtime.phase_two.resume(run_id, protected)
        except _Rejected as rejection:
            return self._error(rejection.code, rejection.status)
        except Exception:
            return self._error(LocalApiErrorCode.INTERNAL_ERROR, 500)
        if result.status is ResultStatus.FAILURE or result.value is None:
            return self._flow_failure(result.failure)
        return _ok(200, result.value)

    @staticmethod
    def _run_id(value: str) -> UUID | None:
        try:
            return _UUID7_ADAPTER.validate_python(value)
        except (TypeError, ValueError, ValidationError):
            return None

    def _flow_failure(self, failure: FailureDetail | None) -> dict[str, object]:
        if failure is None:
            return self._error(LocalApiErrorCode.INTERNAL_ERROR, 500)
        if failure.kind is FailureKind.NOT_FOUND:
            error, status = LocalApiErrorCode.NOT_FOUND, 404
        elif failure.kind is FailureKind.VALIDATION_FAILURE:
            error, status = LocalApiErrorCode.BAD_REQUEST, 400
        elif failure.kind is FailureKind.POLICY_DENIAL:
            error, status = LocalApiErrorCode.POLICY_DENIED, 403
        elif failure.kind in {
            FailureKind.IDEMPOTENCY_CONFLICT,
            FailureKind.RECOVERY_REQUIREMENT,
            FailureKind.ILLEGAL_STATE_TRANSITION,
        }:
            error, status = LocalApiErrorCode.CONFLICT, 409
        elif failure.kind in {
            FailureKind.DEPENDENCY_UNAVAILABLE,
            FailureKind.STORAGE_FAILURE,
            FailureKind.PROVIDER_FAILURE,
            FailureKind.TOOL_ADAPTER_FAILURE,
        }:
            error, status = LocalApiErrorCode.DEPENDENCY_UNAVAILABLE, 503
        else:
            error, status = LocalApiErrorCode.WORKFLOW_FAILED, 422
        return self._error(
            error,
            status,
            failure_kind=failure.kind,
            failure_code=failure.code,
            retryable=failure.retryable,
        )

    @staticmethod
    def _error(
        code: LocalApiErrorCode,
        status: int,
        *,
        failure_kind: FailureKind | None = None,
        failure_code: str | None = None,
        retryable: bool = False,
    ) -> dict[str, object]:
        return _response(
            status,
            LocalApiErrorResponse(
                error=code,
                failure_kind=failure_kind,
                failure_code=failure_code,
                retryable=retryable,
            ),
        )


class _EmptyRequest(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}

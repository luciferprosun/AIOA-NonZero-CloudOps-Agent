"""Fixed W1-W4 composition for the authenticated W5 judge hero."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from uuid import UUID

from pydantic import Field

from aioa_cloudops_agent.agent.local_hitl import LocalOperatorPrincipal
from aioa_cloudops_agent.config import RuntimeSettings
from aioa_cloudops_agent.nz import (
    ResultStatus,
    generate_event_id,
    generate_proposal_id,
    generate_run_id,
    generate_trace_id,
)
from aioa_cloudops_agent.nz.contracts import NonZeroContract
from aioa_cloudops_agent.nz.identifiers import Sha256Digest, Uuid7Identifier
from aioa_cloudops_agent.persistence.local_integrity import (
    LocalIntegrityError,
    atomic_write_private_json,
    open_local_payload,
    read_private_json,
    seal_local_payload,
)
from aioa_cloudops_agent.providers import MockModelProvider, MockToolCall
from aioa_cloudops_agent.workspace import (
    WORKSPACE_REMEDIATION_V1,
    LocalFileWorkspaceAuthorityRepository,
    MaterializedWorkspace,
    WorkspaceAtomicPatchExecutor,
    WorkspaceAuthorityDenied,
    WorkspaceAuthorityService,
    WorkspaceAuthorityState,
    WorkspaceEvidenceService,
    WorkspaceIndependentVerifier,
    WorkspaceJail,
    WorkspacePatchProposal,
    WorkspacePatchProposalBuilder,
    WorkspaceRef,
    WorkspaceRemediationKind,
    WorkspaceVerificationBoundary,
    WorkspaceVerificationDisposition,
    canonical_workspace_json_digest,
    create_workspace_investigation_agent,
    decision_for_request,
    materialize_sealed_fixture,
)

from .workspace_hero_contracts import (
    WORKSPACE_HERO_SCENARIO_ID,
    WorkspaceHeroAfterProof,
    WorkspaceHeroApprovalCard,
    WorkspaceHeroDecisionRequest,
    WorkspaceHeroProjection,
    WorkspaceHeroReplayView,
    WorkspaceHeroStartRequest,
    WorkspaceHeroTimelineCategory,
    WorkspaceHeroTimelineItem,
    WorkspaceHeroTimelineStatus,
    WorkspaceHeroVerificationView,
)
from .workspace_hero_fixture import ensure_workspace_hero_fixture

_MANIFEST_PAYLOAD_TYPE = "AIOA_W5_WORKSPACE_HERO_V1"
_ROOT_CAUSE = (
    "The long inline dockerCommand is being interpreted as a file name instead of a startup "
    "program; the fixed executable removes the quoting ambiguity."
)
_ALTERNATIVE_HYPOTHESIS = (
    "A missing bootstrap value could also prevent startup, so the fixed verifier tests the "
    "fail-closed path independently."
)
_AGENT_FINAL_TEXT = f"""FACTS
- deployment.log records exit 127 and File name too long.
AGENT_INFERENCE
- {_ROOT_CAUSE}
ALTERNATIVE_HYPOTHESIS
- {_ALTERNATIVE_HYPOTHESIS}
HUMAN_DECISION_REQUIRED
- The exact W2 patch remains inert until a durable W3 decision."""


class WorkspaceHeroFailure(RuntimeError):
    """Normalized W5 failure that never carries private host details."""

    def __init__(self, code: str, *, status: int = 409, retryable: bool = False) -> None:
        self.code = code
        self.status = status
        self.retryable = retryable
        super().__init__(code)


def _certified_w4_profile() -> object:
    """Load the exact repository-owned W4 profile only when verification begins."""

    try:
        from scripts.w4_render_start_profile import RenderStartContractV1Profile
    except ImportError as error:
        raise WorkspaceHeroFailure(
            "WORKSPACE_HERO_TRUSTED_PROFILE_UNAVAILABLE",
            status=503,
            retryable=True,
        ) from error
    return RenderStartContractV1Profile()


class _WorkspaceHeroManifest(NonZeroContract):
    schema_version: int = Field(default=1, ge=1, le=1)
    scenario_id: str = Field(pattern=r"^FAILED_RENDER_DEPLOYMENT_VERIFIED_FIX_V1$")
    run_id: Uuid7Identifier
    trace_id: Uuid7Identifier
    workspace_id: Uuid7Identifier
    proposal_id: Uuid7Identifier
    root_digest: Sha256Digest
    workspace_root_name: str = Field(
        min_length=12,
        max_length=96,
        pattern=r"^aioa-w1-[0-9a-f]{8}-[A-Za-z0-9_-]+$",
    )
    replay_proven: bool = False


class _WorkspaceHeroContext:
    def __init__(
        self,
        manifest: _WorkspaceHeroManifest,
        materialized: MaterializedWorkspace,
        repository: LocalFileWorkspaceAuthorityRepository,
    ) -> None:
        self.manifest = manifest
        self.materialized = materialized
        self.repository = repository


class WorkspaceHeroOrchestrator:
    """Compose certified services; never become a second authority implementation."""

    def __init__(
        self,
        root: Path,
        runtime_settings: RuntimeSettings,
        *,
        nonce_deriver: Callable[[str], str],
        profile_factory: Callable[[], object] = _certified_w4_profile,
        clock: Callable[[], datetime] | None = None,
        run_id_factory: Callable[[], UUID] = generate_run_id,
        trace_id_factory: Callable[[], UUID] = generate_trace_id,
        workspace_id_factory: Callable[[], UUID] = generate_event_id,
        proposal_id_factory: Callable[[], UUID] = generate_proposal_id,
        event_id_factory: Callable[[], UUID] = generate_event_id,
        effect_id_factory: Callable[[], UUID] = generate_event_id,
    ) -> None:
        if not isinstance(root, Path) or not isinstance(runtime_settings, RuntimeSettings):
            raise TypeError("workspace hero root and runtime settings are required")
        factories = (
            nonce_deriver,
            profile_factory,
            clock or datetime.now,
            run_id_factory,
            trace_id_factory,
            workspace_id_factory,
            proposal_id_factory,
            event_id_factory,
            effect_id_factory,
        )
        if not all(callable(value) for value in factories):
            raise TypeError("workspace hero factories must be callable")
        if ".." in root.parts or not str(root).strip():
            raise ValueError("workspace hero root is invalid")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root.chmod(0o700)
        if root.is_symlink() or not root.is_dir():
            raise ValueError("workspace hero root must be a real directory")
        self._root = root
        self._runs = root / "runs"
        self._runs.mkdir(mode=0o700, exist_ok=True)
        self._runs.chmod(0o700)
        self._fixture = ensure_workspace_hero_fixture(root / "fixture")
        self._runtime_settings = runtime_settings
        self._nonce_deriver = nonce_deriver
        self._profile_factory = profile_factory
        self._clock = clock or (lambda: datetime.now(UTC))
        self._run_id_factory = run_id_factory
        self._trace_id_factory = trace_id_factory
        self._workspace_id_factory = workspace_id_factory
        self._proposal_id_factory = proposal_id_factory
        self._event_id_factory = event_id_factory
        self._effect_id_factory = effect_id_factory
        self._lock = RLock()

    def start(self, request: WorkspaceHeroStartRequest) -> WorkspaceHeroProjection:
        """Run W1 reasoning and materialize one exact inert W2 proposal."""

        if not isinstance(request, WorkspaceHeroStartRequest):
            raise WorkspaceHeroFailure("WORKSPACE_HERO_SCENARIO_INVALID", status=400)
        with self._lock:
            run_id = self._run_id_factory()
            trace_id = self._trace_id_factory()
            run_directory = self._run_directory(run_id)
            try:
                run_directory.mkdir(mode=0o700, parents=False, exist_ok=False)
                workspace_parent = run_directory / "workspaces"
                workspace_parent.mkdir(mode=0o700)
                materialized = materialize_sealed_fixture(
                    run_id=run_id,
                    fixture_source=self._fixture,
                    workspace_parent=workspace_parent,
                    profile=WORKSPACE_REMEDIATION_V1,
                    workspace_id_factory=self._workspace_id_factory,
                )
                service = WorkspaceEvidenceService(
                    WorkspaceJail(materialized),
                    trace_id=trace_id,
                    clock=self._clock,
                    event_id_factory=self._event_id_factory,
                )
                model = MockModelProvider(
                    tool_plan=(
                        MockToolCall("inspect_deployment_incident", {}),
                        MockToolCall("list_workspace_artifacts", {}),
                        MockToolCall(
                            "read_workspace_artifact",
                            {"relative_path": "deployment.log"},
                        ),
                        MockToolCall(
                            "read_workspace_artifact",
                            {"relative_path": "render.yaml"},
                        ),
                        MockToolCall(
                            "read_workspace_artifact",
                            {"relative_path": "scripts/render_start.sh"},
                        ),
                        MockToolCall(
                            "read_workspace_artifact",
                            {"relative_path": "expected_runtime_contract.json"},
                        ),
                        MockToolCall(
                            "hash_workspace_artifact",
                            {"relative_path": "render.yaml"},
                        ),
                        MockToolCall(
                            "hash_workspace_artifact",
                            {"relative_path": "scripts/render_start.sh"},
                        ),
                        MockToolCall(
                            "hash_workspace_artifact",
                            {"relative_path": "expected_runtime_contract.json"},
                        ),
                    ),
                    final_text=_AGENT_FINAL_TEXT,
                )
                agent_runtime = create_workspace_investigation_agent(
                    service,
                    materialized.ref,
                    runtime_settings=self._runtime_settings,
                    model=model,
                )
                agent_result = agent_runtime.agent(
                    "Investigate why this deployment failed and propose the smallest safe fix."
                )
                if str(agent_result).rstrip() != _AGENT_FINAL_TEXT or model.network_calls != 0:
                    raise WorkspaceHeroFailure("WORKSPACE_HERO_REASONING_UNPROVEN")
                built = WorkspacePatchProposalBuilder(
                    service,
                    clock=self._clock,
                    proposal_id_factory=self._proposal_id_factory,
                ).build(
                    materialized.ref,
                    WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE,
                    evidence_receipts=service.evidence_timeline,
                )
                if built.status is ResultStatus.FAILURE or built.value is None:
                    raise WorkspaceHeroFailure("WORKSPACE_HERO_PROPOSAL_FAILED")
                repository = LocalFileWorkspaceAuthorityRepository(
                    run_directory / "authority.json",
                    clock=self._clock,
                    event_id_factory=self._event_id_factory,
                )
                authority = WorkspaceAuthorityService(repository, clock=self._clock)
                proposal = authority.persist_proposal(built.value)
                manifest = _WorkspaceHeroManifest(
                    scenario_id=WORKSPACE_HERO_SCENARIO_ID,
                    run_id=run_id,
                    trace_id=trace_id,
                    workspace_id=materialized.ref.workspace_id,
                    proposal_id=proposal.proposal_id,
                    root_digest=materialized.ref.root_digest,
                    workspace_root_name=materialized.root.name,
                )
                self._save_manifest(manifest)
                return self._projection(
                    _WorkspaceHeroContext(manifest, materialized, repository)
                )
            except WorkspaceHeroFailure:
                raise
            except Exception as error:
                raise WorkspaceHeroFailure(
                    "WORKSPACE_HERO_START_UNAVAILABLE",
                    status=503,
                    retryable=True,
                ) from error

    def get(self, run_id: UUID) -> WorkspaceHeroProjection:
        with self._lock:
            return self._projection(self._load_context(run_id))

    def request_approval(
        self,
        run_id: UUID,
        principal: LocalOperatorPrincipal,
    ) -> WorkspaceHeroProjection:
        """Persist the exact W3 request; return no nonce or raw internal record."""

        self._require_principal(principal)
        with self._lock:
            context = self._load_context(run_id)
            authority = WorkspaceAuthorityService(context.repository, clock=self._clock)
            try:
                existing = context.repository.get_request(context.manifest.proposal_id)
                if existing is None:
                    authority.begin_approval(context.manifest.proposal_id)
                    authority.record_interrupt(
                        context.manifest.proposal_id,
                        f"w5:{context.manifest.run_id}:{context.manifest.proposal_id}",
                    )
            except WorkspaceAuthorityDenied as error:
                raise WorkspaceHeroFailure(error.code) from error
            return self._projection(context)

    def decide(
        self,
        run_id: UUID,
        request: WorkspaceHeroDecisionRequest,
        principal: LocalOperatorPrincipal,
    ) -> WorkspaceHeroProjection:
        """Derive the complete W3 resume from durable truth and an authenticated human."""

        self._require_principal(principal)
        if not isinstance(request, WorkspaceHeroDecisionRequest):
            raise WorkspaceHeroFailure("WORKSPACE_HERO_DECISION_INVALID", status=400)
        with self._lock:
            context = self._load_context(run_id)
            durable_request = context.repository.get_request(context.manifest.proposal_id)
            if durable_request is None:
                raise WorkspaceHeroFailure("WORKSPACE_HERO_APPROVAL_REQUEST_MISSING")
            if request.request_fingerprint != durable_request.request_hash:
                raise WorkspaceHeroFailure("WORKSPACE_HERO_STALE_APPROVAL_REQUEST", status=403)
            nonce = self._nonce_deriver(durable_request.request_hash)
            try:
                response = decision_for_request(
                    durable_request,
                    decision=request.decision,
                    actor_session_id=principal.actor_session_id,
                    decision_nonce=nonce,
                )
                WorkspaceAuthorityService(
                    context.repository,
                    clock=self._clock,
                ).decide(response)
            except WorkspaceAuthorityDenied as error:
                raise WorkspaceHeroFailure(error.code, status=403) from error
            return self._projection(context)

    def resume(
        self,
        run_id: UUID,
        request: object,
        principal: LocalOperatorPrincipal,
    ) -> WorkspaceHeroProjection:
        """Apply once, or demonstrate consumed-approval replay without a second effect."""

        self._require_principal(principal)
        from .workspace_hero_contracts import WorkspaceHeroResumeRequest

        if not isinstance(request, WorkspaceHeroResumeRequest):
            raise WorkspaceHeroFailure("WORKSPACE_HERO_RESUME_INVALID", status=400)
        with self._lock:
            context = self._load_context(run_id)
            record = self._record(context)
            if record.state is WorkspaceAuthorityState.SUCCESS_WITH_EVIDENCE:
                self._prove_replay(context, principal)
                return self._projection(self._load_context(run_id))
            if record.state is WorkspaceAuthorityState.DENIED_BY_HUMAN:
                raise WorkspaceHeroFailure("WORKSPACE_HERO_DENIED_TERMINAL", status=403)
            if record.state is WorkspaceAuthorityState.PATCH_APPLIED_UNVERIFIED:
                return self._projection(context)
            if record.state is not WorkspaceAuthorityState.APPROVED:
                raise WorkspaceHeroFailure("WORKSPACE_HERO_APPLY_NOT_APPROVED", status=403)
            try:
                executor = WorkspaceAtomicPatchExecutor(
                    WorkspaceJail(context.materialized),
                    context.repository,
                    clock=self._clock,
                    effect_id_factory=self._effect_id_factory,
                )
                result = executor.apply(context.manifest.proposal_id)
            except Exception as error:
                raise WorkspaceHeroFailure("WORKSPACE_HERO_APPLY_UNAVAILABLE") from error
            if result.status is ResultStatus.FAILURE or result.value is None:
                code = (
                    "WORKSPACE_HERO_APPLY_FAILED"
                    if result.failure is None
                    else result.failure.code
                )
                raise WorkspaceHeroFailure(code)
            return self._projection(context)

    def verify_or_reconcile(
        self,
        run_id: UUID,
        principal: LocalOperatorPrincipal,
    ) -> WorkspaceHeroProjection:
        """Invoke the exact W4 proposal-id-only verifier and project persisted truth."""

        self._require_principal(principal)
        with self._lock:
            context = self._load_context(run_id)
            record = self._record(context)
            if record.state is WorkspaceAuthorityState.DENIED_BY_HUMAN:
                raise WorkspaceHeroFailure("WORKSPACE_HERO_DENIED_NOT_VERIFIABLE", status=403)
            verifier = self._verifier(context)
            result = verifier.verify(context.manifest.proposal_id)
            if result.status is ResultStatus.FAILURE or result.value is None:
                code = (
                    "WORKSPACE_HERO_VERIFICATION_FAILED"
                    if result.failure is None
                    else result.failure.code
                )
                raise WorkspaceHeroFailure(code, status=422)
            return self._projection(context)

    def _prove_replay(
        self,
        context: _WorkspaceHeroContext,
        principal: LocalOperatorPrincipal,
    ) -> None:
        durable_request = context.repository.get_request(context.manifest.proposal_id)
        decision = context.repository.get_decision(context.manifest.proposal_id)
        if durable_request is None or decision is None:
            raise WorkspaceHeroFailure("WORKSPACE_HERO_REPLAY_AUTHORITY_MISSING")
        nonce = self._nonce_deriver(durable_request.request_hash)
        response = decision_for_request(
            durable_request,
            decision=decision.decision,
            actor_session_id=principal.actor_session_id,
            decision_nonce=nonce,
        )
        try:
            _record, reconciled = WorkspaceAuthorityService(
                context.repository,
                clock=self._clock,
            ).decide(response)
        except WorkspaceAuthorityDenied as error:
            raise WorkspaceHeroFailure(error.code, status=403) from error
        verified = self._verifier(context).verify(context.manifest.proposal_id)
        if (
            not reconciled
            or verified.status is ResultStatus.FAILURE
            or verified.value is None
            or verified.value.verifier_fixed_process_probes != 0
        ):
            raise WorkspaceHeroFailure("WORKSPACE_HERO_REPLAY_PROOF_FAILED")
        self._save_manifest(context.manifest.model_copy(update={"replay_proven": True}))

    def _verifier(self, context: _WorkspaceHeroContext) -> WorkspaceIndependentVerifier:
        return WorkspaceIndependentVerifier(
            WorkspaceVerificationBoundary(context.materialized, self._fixture),
            context.repository,
            self._profile_factory(),
            clock=self._clock,
            evidence_id_factory=self._event_id_factory,
        )

    def _projection(self, context: _WorkspaceHeroContext) -> WorkspaceHeroProjection:
        snapshot = context.repository.read_snapshot()
        record = next(
            (
                item
                for item in snapshot.proposals
                if item.proposal.proposal_id == context.manifest.proposal_id
            ),
            None,
        )
        if record is None:
            raise WorkspaceHeroFailure("WORKSPACE_HERO_PROPOSAL_NOT_FOUND", status=404)
        proposal = WorkspacePatchProposal.model_validate(record.proposal.model_dump(mode="python"))
        approval_request = context.repository.get_request(proposal.proposal_id)
        decision = context.repository.get_decision(proposal.proposal_id)
        apply_receipt = context.repository.get_receipt(proposal.proposal_id)
        report = context.repository.get_verification_report(proposal.proposal_id)
        verification_receipt = context.repository.get_verification_receipt(
            proposal.proposal_id
        )
        verified = (
            report is not None
            and verification_receipt is not None
            and report.disposition is WorkspaceVerificationDisposition.VERIFIED
            and record.state is WorkspaceAuthorityState.SUCCESS_WITH_EVIDENCE
        )
        verification = None
        if verified:
            assert report is not None and verification_receipt is not None
            verification = WorkspaceHeroVerificationView(
                disposition="VERIFIED",
                report_fingerprint=report.report_digest,
                receipt_fingerprint=verification_receipt.receipt_digest,
                proof_origin=verification_receipt.proof_origin.value,
                checks_passed=sum(check.status.value == "PASS" for check in report.checks),
                checks_total=len(report.checks),
            )
        after_status = "PASS" if verified else "PENDING"
        after = WorkspaceHeroAfterProof(
            patch_scope="EXACT" if verified else "PENDING",
            target_hash="MATCH" if verified else "PENDING",
            startup_executable="FIXED" if verified else "PENDING",
            token_mode="0600" if verified else "PENDING",
            bootstrap_secret_in_child_env="ABSENT" if verified else "PENDING",
            health=after_status,
            ready=after_status,
            external_egress=0,
            aws_calls=0,
            final="SUCCESS_WITH_EVIDENCE" if verified else "PENDING",
        )
        human_decision = "PENDING" if decision is None else decision.decision.value
        replay = None
        if verified:
            replay = WorkspaceHeroReplayView(
                status=(
                    "REPLAY_REJECTED_RECONCILED"
                    if context.manifest.replay_proven
                    else "AVAILABLE"
                ),
                approval_already_consumed=decision is not None,
                patch_apply_count=1,
            )
        approval_card = WorkspaceHeroApprovalCard(
            workspace_fingerprint=proposal.base_root_digest,
            proposal_fingerprint=proposal.proposal_digest,
            patch_fingerprint=proposal.patch_digest,
            request_fingerprint=(
                None if approval_request is None else approval_request.request_hash
            ),
            evidence=(
                "deployment.log",
                "render.yaml",
                "scripts/render_start.sh",
                "expected_runtime_contract.json",
            ),
            expected_verification=(
                "render_start_contract_v1",
                "token file mode 0600",
                "secret absent from child env",
                "/health 200",
                "/ready 200",
            ),
            rollback=proposal.rollback_strategy,
        )
        return WorkspaceHeroProjection(
            run_id=proposal.run_id,
            state=record.state,
            success_with_evidence=verified,
            incident_facts=(
                "Image build completed successfully.",
                "Runtime exited with status 127.",
                "The deployment log contains File name too long.",
            ),
            root_cause=_ROOT_CAUSE,
            alternative_hypothesis=_ALTERNATIVE_HYPOTHESIS,
            approval_card=approval_card,
            patch_diff=proposal.preview.unified_diff,
            after=after,
            verification=verification,
            human_decision=human_decision,
            workspace_mutation_count=int(apply_receipt is not None),
            executor_receipt_present=apply_receipt is not None,
            verification_receipt_present=verification_receipt is not None,
            replay=replay,
            timeline=self._timeline(
                context.manifest,
                proposal,
                record.state,
                approval_request,
                decision,
                apply_receipt,
                report,
                verification_receipt,
            ),
        )

    @staticmethod
    def _timeline(
        manifest: _WorkspaceHeroManifest,
        proposal: WorkspacePatchProposal,
        state: WorkspaceAuthorityState,
        request: object,
        decision: object,
        receipt: object,
        report: object,
        verification_receipt: object,
    ) -> tuple[WorkspaceHeroTimelineItem, ...]:
        denied = state is WorkspaceAuthorityState.DENIED_BY_HUMAN
        succeeded = state is WorkspaceAuthorityState.SUCCESS_WITH_EVIDENCE
        decision_digest = getattr(decision, "decision_hash", None)
        receipt_digest = (
            None
            if receipt is None
            else canonical_workspace_json_digest(receipt.model_dump(mode="json"))
        )
        report_digest = getattr(report, "report_digest", None)
        verification_digest = getattr(verification_receipt, "receipt_digest", None)

        def item(
            stage: str,
            category: WorkspaceHeroTimelineCategory,
            status: WorkspaceHeroTimelineStatus,
            title: str,
            summary: str,
            source: str,
            fingerprint: str | None,
        ) -> WorkspaceHeroTimelineItem:
            return WorkspaceHeroTimelineItem(
                stage=stage,
                category=category,
                status=status,
                title=title,
                summary=summary,
                authority_source=source,
                evidence_fingerprint=fingerprint,
            )

        if decision is None:
            human_status = WorkspaceHeroTimelineStatus.CURRENT
        else:
            human_status = WorkspaceHeroTimelineStatus.COMPLETE
        if denied:
            effect_status = verification_status = receipt_status = (
                WorkspaceHeroTimelineStatus.SAFE_STOP
            )
        else:
            effect_status = (
                WorkspaceHeroTimelineStatus.COMPLETE
                if receipt is not None
                else (
                    WorkspaceHeroTimelineStatus.CURRENT
                    if state is WorkspaceAuthorityState.APPROVED
                    else WorkspaceHeroTimelineStatus.PENDING
                )
            )
            verification_status = (
                WorkspaceHeroTimelineStatus.COMPLETE
                if report is not None
                else (
                    WorkspaceHeroTimelineStatus.CURRENT
                    if receipt is not None
                    else WorkspaceHeroTimelineStatus.PENDING
                )
            )
            receipt_status = (
                WorkspaceHeroTimelineStatus.COMPLETE
                if verification_receipt is not None
                else WorkspaceHeroTimelineStatus.PENDING
            )
        replay_status = (
            WorkspaceHeroTimelineStatus.COMPLETE
            if manifest.replay_proven
            else (
                WorkspaceHeroTimelineStatus.CURRENT
                if succeeded
                else WorkspaceHeroTimelineStatus.PENDING
            )
        )
        return (
            item(
                "OBSERVE",
                WorkspaceHeroTimelineCategory.FACT,
                WorkspaceHeroTimelineStatus.COMPLETE,
                "Incident observed",
                "Image build succeeded; runtime failed with exit 127 and File name too long.",
                "W1 bounded inspection",
                proposal.base_root_digest,
            ),
            item(
                "EVIDENCE",
                WorkspaceHeroTimelineCategory.FACT,
                WorkspaceHeroTimelineStatus.COMPLETE,
                "Evidence captured",
                "Four allowlisted artifacts were read or hashed inside the sealed workspace.",
                "W1 evidence receipts",
                proposal.evidence_digest,
            ),
            item(
                "ROOT_CAUSE",
                WorkspaceHeroTimelineCategory.AGENT_INFERENCE,
                WorkspaceHeroTimelineStatus.COMPLETE,
                "Root cause inferred",
                _ROOT_CAUSE,
                "Strands reasoning over W1 evidence",
                proposal.evidence_digest,
            ),
            item(
                "PATCH_PROPOSAL",
                WorkspaceHeroTimelineCategory.PATCH_PROPOSAL,
                WorkspaceHeroTimelineStatus.COMPLETE,
                "Exact patch proposed",
                "W2 generated one content-addressed render.yaml replacement; it grants no authority.",
                "W2 server builder",
                proposal.proposal_digest,
            ),
            item(
                "POLICY",
                WorkspaceHeroTimelineCategory.POLICY_DECISION,
                WorkspaceHeroTimelineStatus.COMPLETE,
                "Policy requires a human",
                "PLAN_AND_CONFIRM binds one exact workspace, base state and patch.",
                "Deterministic policy",
                proposal.patch_digest,
            ),
            item(
                "HUMAN_DECISION",
                WorkspaceHeroTimelineCategory.HUMAN_DECISION,
                human_status,
                "Human decision",
                "The exact request is approved or denied through durable W3 authority.",
                "W3 durable human authority",
                decision_digest or getattr(request, "request_hash", None),
            ),
            item(
                "PATCH_EFFECT",
                WorkspaceHeroTimelineCategory.ACTION,
                effect_status,
                "Atomic effect",
                (
                    "Denied safely; workspace mutation delta is zero."
                    if denied
                    else "W3 applies exactly one render.yaml replacement and stops unverified."
                ),
                "W3 at-most-once executor",
                receipt_digest,
            ),
            item(
                "VERIFICATION",
                WorkspaceHeroTimelineCategory.VERIFICATION,
                verification_status,
                "Independent verification",
                (
                    "Not run after denial."
                    if denied
                    else "W4 reopens disk truth and runs only render_start_contract_v1."
                ),
                "W4 independent verifier",
                report_digest,
            ),
            item(
                "RECEIPT",
                WorkspaceHeroTimelineCategory.VERIFICATION,
                receipt_status,
                "Evidence-bound receipt",
                (
                    "No receipt exists after denial."
                    if denied
                    else "Only a persisted verified report permits SUCCESS_WITH_EVIDENCE."
                ),
                "W4 durable verification receipt",
                verification_digest,
            ),
            item(
                "RECOVERY_REPLAY",
                WorkspaceHeroTimelineCategory.RECOVERY_REPLAY,
                replay_status,
                "Recovery and replay",
                "W4 recovery is certified; consumed approval cannot create a second effect.",
                "W3/W4 reconciliation",
                verification_digest,
            ),
        )

    def _load_context(self, run_id: UUID) -> _WorkspaceHeroContext:
        manifest = self._load_manifest(run_id)
        run_directory = self._run_directory(run_id)
        workspace_root = run_directory / "workspaces" / manifest.workspace_root_name
        materialized = MaterializedWorkspace(
            ref=WorkspaceRef(
                run_id=manifest.run_id,
                workspace_id=manifest.workspace_id,
                fixture_version="workspace_render_incident_v1",
                root_digest=manifest.root_digest,
                created_from_digest=manifest.root_digest,
            ),
            root=workspace_root,
            profile=WORKSPACE_REMEDIATION_V1,
        )
        repository = LocalFileWorkspaceAuthorityRepository(
            run_directory / "authority.json",
            clock=self._clock,
            event_id_factory=self._event_id_factory,
        )
        return _WorkspaceHeroContext(manifest, materialized, repository)

    def _record(self, context: _WorkspaceHeroContext):
        record = context.repository.get_proposal_record(context.manifest.proposal_id)
        if record is None:
            raise WorkspaceHeroFailure("WORKSPACE_HERO_PROPOSAL_NOT_FOUND", status=404)
        return record

    def _run_directory(self, run_id: UUID) -> Path:
        if not isinstance(run_id, UUID):
            raise WorkspaceHeroFailure("WORKSPACE_HERO_RUN_ID_INVALID", status=400)
        return self._runs / str(run_id)

    def _manifest_path(self, run_id: UUID) -> Path:
        return self._run_directory(run_id) / "manifest.json"

    def _save_manifest(self, manifest: _WorkspaceHeroManifest) -> None:
        try:
            atomic_write_private_json(
                self._manifest_path(manifest.run_id),
                seal_local_payload(
                    manifest.model_dump(mode="json"),
                    payload_type=_MANIFEST_PAYLOAD_TYPE,
                ),
            )
        except (OSError, LocalIntegrityError, TypeError, ValueError) as error:
            raise WorkspaceHeroFailure(
                "WORKSPACE_HERO_MANIFEST_UNAVAILABLE",
                status=503,
                retryable=True,
            ) from error

    def _load_manifest(self, run_id: UUID) -> _WorkspaceHeroManifest:
        path = self._manifest_path(run_id)
        if not path.exists():
            raise WorkspaceHeroFailure("WORKSPACE_HERO_RUN_NOT_FOUND", status=404)
        try:
            payload, _digest = open_local_payload(
                read_private_json(path, max_bytes=32_768),
                payload_type=_MANIFEST_PAYLOAD_TYPE,
            )
            manifest = _WorkspaceHeroManifest.model_validate(payload)
        except (OSError, LocalIntegrityError, TypeError, ValueError) as error:
            raise WorkspaceHeroFailure(
                "WORKSPACE_HERO_MANIFEST_UNAVAILABLE",
                status=503,
                retryable=True,
            ) from error
        if manifest.run_id != run_id or manifest.scenario_id != WORKSPACE_HERO_SCENARIO_ID:
            raise WorkspaceHeroFailure("WORKSPACE_HERO_RUN_BINDING_MISMATCH", status=403)
        return manifest

    @staticmethod
    def _require_principal(principal: LocalOperatorPrincipal) -> None:
        if not isinstance(principal, LocalOperatorPrincipal):
            raise WorkspaceHeroFailure("WORKSPACE_HERO_OPERATOR_REQUIRED", status=401)

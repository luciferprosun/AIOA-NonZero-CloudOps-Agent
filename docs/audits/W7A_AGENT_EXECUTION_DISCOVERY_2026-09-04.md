# W7A Agent Execution Discovery, Freeze Map & Reuse Audit

Date: 2026-09-04
Phase: W7A Phase 1 of 15
Scope: source-level discovery only; no Phase 2 implementation

## 1. Executive summary

The frozen W7 candidate is intact and is a strong base for the planned
`HYBRID_NARROW_PLUS_CODEX_HARNESS` architecture. AIOA already contains the security-critical
control-plane pieces that must remain authoritative: closed capability policy, exact durable human
approval, content-addressed proposals, atomic single-effect application, replay/idempotency
ownership, independent verification, recovery reconciliation, identity-linked evidence, local
secret scanning, and a sealed workspace jail.

The repository does **not** contain a general coding worker, Codex App Server adapter, GitHub API
client, GitHub MCP client, disposable repository sandbox provider, arbitrary bounded command
runner, or skills registry. Those are real gaps, not hidden implementations. Existing release
scripts contain useful Git and subprocess patterns, but they are purpose-specific scripts or
dependency-injected protocols rather than an execution subsystem.

The smallest safe path is therefore extension, not replatforming:

1. Keep Non-Zero policy, durable authority, evidence and replay logic as the control plane.
2. Add a thin coding-worker adapter beside the existing agent runtime wrappers.
3. Bind all future worker output to existing UUIDv7 identities and canonical SHA-256 contracts.
4. Generalize the sealed-workspace and exact-patch types without weakening their current bounds.
5. Add disposable process/container isolation as a provider; do not mistake a Git worktree or the
   current application image for a security sandbox.
6. Keep GitHub reads and writes separate: read-only MCP context first, deterministic authority-bound
   branch/commit/push/PR actuation later. The remote ceiling remains a verified Pull Request.

Discovery classification: **3 PRESENT, 9 PARTIAL, 3 MISSING, 0 CONFLICTING**.

## 2. Frozen baseline verification

| Item | Observed value | Result |
| --- | --- | --- |
| Repository | `/media/l/LSC_DATA/AWS_HACKATHON/AIOA-NonZero-CloudOps-Agent` | PASS |
| Frozen branch before branching | `codex/w7-final-release-candidate` | PASS |
| Expected frozen HEAD | `945c87052815b237004d259fe993cc92cbd579b7` | PASS |
| Observed frozen HEAD | `945c87052815b237004d259fe993cc92cbd579b7` | PASS |
| Initial worktree | clean (`git status --short` empty) | PASS |
| W7A branch | `codex/w7a-agent-execution-slice` created locally from exact frozen HEAD | PASS |
| Remote W7A branch | absent; no push performed | PASS |
| Python | 3.12.3 | observed |
| Node / npm | 18.19.1 / 9.2.0 | observed only; not installed or changed |
| Relevant tags | no W7/B5/B6 tag names present | observed |

Frozen status is established by
`docs/audits/W7_FINAL_RELEASE_CANDIDATE_2026-09-04.md`: W7 PASS, B5 BUILD_COMPLETE,
B6 PASS_LOCAL_ONLY, W8 not authorized, and zero AWS calls/deployments/remote pushes. Supporting
authority files are present at:

- `docs/evidence/release/w7-b5-recertification-state.json`
- `docs/evidence/release/w7-release-manifest.json`
- `docs/evidence/release/w7-container-hero.json`
- `docs/evidence/submission/w7-b6-reproducibility.json`
- `docs/evidence/submission/w7-b6-final-public-scan.json`
- `docs/evidence/submission/w7-publication-bundle.json`

The five frozen input hashes recorded before Phase 1 documentation was created were:

| Path | SHA-256 |
| --- | --- |
| `docs/audits/W7_FINAL_RELEASE_CANDIDATE_2026-09-04.md` | `0cef86eeb1e4ed4fa702c5f45e1208515734c84f2cdd7a3372a4e2b057732774` |
| `docs/evidence/release/w7-b5-recertification-state.json` | `d76b42c197fd1d0763fa37c3d06262d29b4fabd10bb7b447b917534a878a2e89` |
| `docs/evidence/release/w7-release-manifest.json` | `cc199b51a535785dd38f0ef0df5369d8f4af7e89b8a280388dd1423f46cc5683` |
| `docs/evidence/submission/w7-publication-bundle.json` | `b89b1c3f017221fe80f939a24105d0625515f52a9f11c836e987d477c9607d6a` |
| `docs/evidence/submission/w7-b6-reproducibility.json` | `3913accf719e33e15e2bb690586ff5fbeebadf64ef7596cac4c4b6a5646f7933` |

All local named branches are ancestors of, or equal to, the frozen W7 HEAD. No post-W7 feature
branch exists. Two preserved stashes contain only deployment-track recovery/security-probe files:
`scripts/operations/run_recovery_readiness.py`,
`tests/integration/test_recovery_readiness.py`, `tests/unit/test_rollback_manifest.py`, and
`scripts/operations/run_security_probes.py`. They were not applied and contain no discovered GitHub,
MCP, coding-worker or sandbox-provider implementation. The W7A worktree had no untracked or
local-only files at preflight.

## 3. Architecture map

### 3.1 Current CloudOps control path

```text
HTTP/Judge adapter
  -> JudgeInvestigationRuntime / LocalFirstPhaseOneFlow
  -> create_primary_agent (one Strands Agent, fixed five tools)
  -> read-only EC2/metrics/evidence tools
  -> durable ActionProposal
  -> DurableApprovalFlow / DurableProposalHumanInTheLoop
  -> private StopSandboxInstance boundary
  -> verification
  -> durable SUCCESS_WITH_EVIDENCE or typed closed failure
  -> RecoveryCoordinator for restart/lost-ACK reconciliation
```

Key entry points are `agent/factory.py:create_primary_agent` (lines 150-330),
`agent/investigation_flow.py:BoundedInvestigationFlow.execute` (lines 77-386),
`agent/approval_flow.py:DurableApprovalFlow` (lines 70-423), and
`recovery/coordinator.py:RecoveryCoordinator` (notably lines 120-424). The primary agent loads no
dynamic tool directory and asserts its exact five-tool surface at `agent/factory.py:294-316`.

### 3.2 Current workspace remediation path

```text
LocalApiApplication protected route
  -> WorkspaceHeroOrchestrator.start
  -> materialize_sealed_fixture
  -> WorkspaceJail + WorkspaceEvidenceService
  -> create_workspace_investigation_agent (fixed five tools, mock/offline)
  -> WorkspacePatchProposalBuilder (inert exact proposal)
  -> LocalFileWorkspaceAuthorityRepository
  -> WorkspaceAuthorityService request + exact human decision
  -> WorkspaceAtomicPatchExecutor.apply (proposal_id only, at-most-once)
  -> PATCH_APPLIED_UNVERIFIED
  -> WorkspaceIndependentVerifier.verify (fixed repository-owned profile)
  -> SUCCESS_WITH_EVIDENCE / reconciliation / typed failure
```

The real W5 composition is in `local_api/workspace_hero.py:147-501`. It creates a per-run private
directory and sealed fixture at lines 182-227, calls the Strands workspace agent at lines 269-279,
persists the proposal at lines 280-308, records human authority at lines 332-389, applies once at
lines 391-434, and verifies independently at lines 436-501. The current hero reasoning uses a fixed
`MockModelProvider` tool plan (`workspace_hero.py:234-268`); it proves orchestration and safety, not
general coding intelligence.

### 3.3 Security ownership boundaries

- The model may select only registered tools; it does not own authority.
- `WorkspaceCapabilityProfile` fixes operations, artifact paths and size limits, with network and
  mutation both false (`workspace/profile.py:17-79`).
- `WorkspaceApprovalPayload` and decision records bind proposal, run, trace, workspace, target,
  before/after hashes, evidence, canonical diff and expiry
  (`workspace/authority_contracts.py:88-322`).
- `LocalFileWorkspaceAuthorityRepository` uses owner-only integrity-wrapped JSON, file locking and
  atomic writes (`workspace/authority_repository.py:93-184`).
- Effect ownership is durable before mutation, and receipts cannot advance beyond
  `PATCH_APPLIED_UNVERIFIED` (`workspace/authority_repository.py:366-436`).
- Independent verification reopens disk state rather than trusting the apply receipt
  (`workspace/verification_boundary.py:64-430`, `workspace/verifier.py:81-862`).

## 4. Discovery matrix

| Domain | Status | Source-level evidence and observed behavior | Reuse decision |
| --- | --- | --- | --- |
| A. Agent orchestration / task state | **PARTIAL** | Fixed Strands runtimes exist in `agent/factory.py:97-330`, `workspace/agent.py:44-132`, `workspace/authority_agent.py:53-306`, and `workspace/verification_agent.py:48-156`. Durable lifecycle, pause/resume and recovery exist in `agent/investigation_flow.py`, `agent/approval_flow.py`, and `recovery/coordinator.py`. There is no generic coding-task/critic/repair-loop worker contract. | Reuse the runtime wrappers, `Run`, checkpoints, `ControlResult`, audit events and HITL semantics. Add a thin worker protocol; do not turn a CloudOps-specific flow into an arbitrary executor. |
| B. Authority / approvals / policy | **PRESENT** | Closed capability mapping in `nz/authority.py:10-61`; exact workspace request/decision/effect contracts in `workspace/authority_contracts.py`; durable transitions in `workspace/authority_repository.py:250-436`; native Strands pause/resume in `workspace/authority_agent.py:162-272`. Tests cover expiry, denial, replay, drift, competing decisions and restart in `tests/integration/test_workspace_human_bound_patch_authority.py:230-927`. | Extend these objects into an Execution Capsule. Never add an independent approval implementation inside a coding worker, MCP adapter or GitHub actuator. |
| C. Evidence / ledger / identity | **PRESENT** | UUIDv7 run/trace/proposal/event identity in `nz/identifiers.py:28-70`; canonical hashing throughout `nz/contracts.py`; evidence timeline in `workspace/evidence.py:35-316`; durable audit events, receipts and reconciliation in `workspace/authority_repository.py`; local and DynamoDB repository implementations in `persistence/`. | Reuse identity, canonical JSON/digests, events, receipts and atomic repository semantics. Add new event types/records only through closed schemas. |
| D. Git primitives | **PARTIAL** | Release-only status/HEAD/origin guards exist in `release/preflight.py:287-330,400-486,678-707` and `release/attestation.py:270-420`. Clean clone and exact checkout exist in `scripts/prove_clean_clone.py:173-184,290-334`; deterministic Git-blob export exists in `scripts/build_public_submission.py:172-206`. No product repository abstraction implements bounded clone/fetch/branch/worktree/diff/commit/status/ref verification. | Extract or wrap only the proven pure checks. Introduce a narrow repository service later, bound to workspace and exact base HEAD. Do not expose raw Git argv to the model. |
| E. GitHub integration | **MISSING** | Search across `src`, `scripts`, tests, config, dependencies and local history found no REST/GraphQL client, GitHub App/PAT provider, repo/issue/PR/Actions/branch-protection adapter or remote write verifier. Git URLs and `git ls-remote` release checks are not a GitHub integration. | Phase 3+ must add read-only GitHub context separately from deterministic writes. No token creation or remote call belongs in Phase 1. |
| F. MCP integration | **MISSING** | Search across source, tests, scripts, docs and history found no MCP client/server, transport, registry, protocol config or tool filter. Existing prompts explicitly deny MCP capability (`workspace/agent.py:27-41`, `workspace/verification_agent.py:37-45`). | Add an explicit read-only adapter later. Keep MCP tools outside the canonical mutation authority and filter their schemas deterministically. |
| G. Shell / command execution | **PARTIAL** | No `subprocess`, `Popen`, shell or process launcher exists under product package `src/aioa_cloudops_agent`. A strong one-purpose runner exists in `scripts/w4_render_start_profile.py:33-255`: fixed argv, private temp cwd, sanitized env, bounded logs, timeout, process group termination and loopback checks. Release modules define injectable `CommandRunner` protocols but require external runners. | Reuse the fixed-runner techniques, not its Render-specific command. A later bounded runner must accept structured argv only, enforce cwd/env/output/time/resource policy, and live behind SandboxProvider. |
| H. Workspace / sandbox | **PARTIAL** | Sealed fixture materialization and artifact-tree identity exist in `workspace/fixture.py:29-264`; path, type, symlink, hardlink and TOCTOU checks in `workspace/jail.py:47-419`; fixed profiles in `workspace/profile.py`. Dockerfile supplies a non-root application image (`Dockerfile:1-69`) and release tests run containers with `--network none`. No disposable arbitrary-repository provider, kernel boundary, resource quotas or credentialless execution capsule exists. | Reuse `WorkspaceRef`, materialization, jail and full-tree digesting. Add `SandboxProvider`/`DisposableWorkspace`; do not treat a Git worktree or Python socket monkeypatch as isolation. |
| I. Patch / code editing | **PARTIAL** | Canonical relative paths/diffs and content-addressed proposal types exist in `workspace/contracts.py:57-598`; inert builder in `workspace/proposal.py:68-461`; proposal-id-only exact apply in `workspace/executor.py:48-611`. Tests prove zero mutation, canonical diff, path/link denial, TOCTOU and at-most-once effect. The implementation is intentionally hard-coded to one `render.yaml` transformation and is not a general multi-file PatchSet. | Generalize the schema and transform registry while preserving canonical before/after hashes, exact scope, O_NOFOLLOW checks, approval binding and atomic replacement. |
| J. Test / validation loop | **PARTIAL** | Fixed verification exists in `workspace/verifier.py` and `scripts/w4_render_start_profile.py`; deterministic P0/P1/B4/B5/B6 gate scripts exist. The repository has no safe model-driven test discovery, targeted selection, bounded repair iteration, critic pass or generic build/lint result contract. Workspace code is explicitly forbidden from executing repository tests (`tests/integration/test_workspace_independent_verification.py:405-437`). | Reuse receipt/check schemas and fixed-profile verification. Later add a sandbox-owned validation plan with explicit iteration and resource budgets; never run repo hooks on the host. |
| K. Package / tool setup | **PARTIAL** | Pinned build/runtime locks and reproducible non-root image build exist in `Dockerfile:1-69`, `requirements/`, `pyproject.toml:1-31`, and clean-clone scripts. There is no runtime installer authority for pip/uv/npm/pnpm/yarn, no project detector, and no credential-isolated setup service. | Use pinned lock/hash and clean-room patterns. Future setup runs only inside disposable sandboxes with egress and credential policy; no host sudo/package installation. |
| L. Secrets / egress | **PARTIAL** | Reusable value-free `scan_files(root, relative_paths)` exists in `scripts/phase3/scan_secrets.py:14-138`; public tree scanner in `scripts/scan_public_submission.py:17-228`; environment stripping in `release/preflight.py:290-330`; process-local loopback guard in `scripts/b4_network_guard.py:16-93`; container builds/tests use no-network proofs. Missing are kernel-enforced per-task egress and a GitHub credential broker/custody boundary. | Extract scanner logic into a stable library and scan proposed patches, evidence and outbound payloads. Enforce network and credential absence at SandboxProvider, not by prompt or monkeypatch alone. |
| M. Prompt-injection defenses | **PARTIAL** | System prompts declare repository content untrusted and model output non-authoritative (`workspace/agent.py:27-41`); callers cannot supply path/content/diff/argv; strict JSON and authority-smuggling tests exist in `tests/integration/test_w6_security_feature_freeze.py:203-356`; path/symlink/secret-sensitive tests in `tests/unit/test_workspace_foundation.py:118-243`. No full malicious-repository fixture, taint labels, instruction/data envelope or coding-worker adversarial corpus exists. | Preserve deterministic post-model validation and add hostile repository fixtures before any worker gets executable capability. Prompt wording is defense in depth only. |
| N. Skills / reusable task packs | **MISSING** | No repository `AGENTS.md`, skills registry, maintenance-pack schema, task template loader or curated python/node/CI skill exists. Static Strands tool tuples are not a skills facility. Searches covered source, tests, scripts, config, docs and history. | Design later as signed/versioned data mapped to fixed capabilities; skills must never register arbitrary tools or expand authority dynamically. |
| O. AWS integrations | **PRESENT** | Read adapters in `aws_clients.py` and `cloudops/`; deterministic AWS authority in `domain/aws_boundary.py`; protected remediation in `remediation/`; read-only verification in `verification/`; local/DynamoDB persistence in `persistence/`; IaC/release guards in `infra/` and `release/`. Tests such as `tests/unit/test_private_sandbox_remediation.py:367-858` prove zero-call denial and bounded stop behavior. | Preserve provider interfaces and Non-Zero authority compatibility. No AWS call was needed or made during this audit. |

## 5. Existing Git/GitHub inventory

### Real Git code

- `release/preflight.py:287-330` defines a command-result protocol and strips AWS/AIOA/provider
  credentials plus global/system Git configuration from child checks.
- `release/preflight.py:400-486` checks exact HEAD, branch, worktree status and `origin/main` through
  an injected runner. The library fails if the runner is absent (`preflight.py:678-707`).
- `release/attestation.py:270-420` repeats exact commit/tree/origin/branch/worktree bindings for
  release attestation.
- `scripts/prove_clean_clone.py:173-184,290-334` selects local/remote clone mode, checks out the
  exact commit and rejects identity mismatch.
- `scripts/build_public_submission.py:172-206` reads exact Git objects into a sanitized publication
  tree.
- `scripts/phase3/scan_secrets.py:141-156` uses `git ls-files` only to enumerate scan input.

These are reachable from release/gate scripts and have unit tests, but they are not a general
repository service. No model-facing Git tool exists. No code creates an arbitrary feature branch,
commits an approved patch, pushes a branch, opens a PR, checks Actions, or re-verifies GitHub remote
state after a mutation.

### GitHub and authentication

No GitHub client or credential provider exists in the repository. `pyproject.toml` contains only
Pydantic, Strands and uuid6 runtime dependencies. No PAT or GitHub App contract exists. Current
local Git authentication is external host state and must not be inherited by future test processes.

### Reachability and history

All named local development branches are included in frozen W7 history. No unmerged post-W7 branch
contains hidden Git/GitHub/MCP work. Two stashes are preserved deployment-recovery work only and
were not applied. No working-tree local-only implementation was found.

## 6. Existing authority, policy and evidence inventory

The future Execution Capsule should extend, not replace, these exact points:

- `nz/authority.py:_CAPABILITY_AUTHORITY` and `require_capability_authority`: closed, typed policy.
- `nz/identifiers.py`: UUIDv7 run, trace, proposal and event identities.
- `workspace/authority_contracts.py:WorkspaceApprovalPayload`: exact human-reviewed material,
  including `canonical_diff_sha256` at lines 88-161.
- `WorkspaceApprovalResumeRequest` and `WorkspaceApprovalDecisionRecord`: actor session, nonce,
  request hash, expiry and immutable decision binding at lines 187-322.
- `WorkspaceEffectOwnership`: durable at-most-once ownership and semantic key
  `workspace-patch:{proposal_digest}` at lines 326-402.
- `PatchApplyReceipt`, `WorkspaceReconciliationMarker`, `WorkspaceAuthorityAuditEvent`: effect and
  recovery evidence at lines 406-503.
- `LocalFileWorkspaceAuthorityRepository._mutate`: locked read-modify-atomic-write at
  `workspace/authority_repository.py:133-184`.
- `WorkspaceAtomicPatchExecutor._pre_effect_revalidate` and `_assert_exact_target_before`:
  base/source/support hash and immediate TOCTOU checks at `workspace/executor.py:342-413`.
- `WorkspaceIndependentVerifier`: independent read-back and durable terminal proof.

For future remote work, extend bindings with repository identity, remote URL/owner, exact base ref
and base HEAD, target branch, canonical PatchSet digest, permitted Git/GitHub operations, sandbox
identity, credential class, expiry and operation identity. Effect ownership must be persisted before
the first remote write. A PR URL or HTTP 2xx alone must never constitute success; exact remote refs,
commit tree and PR metadata must be independently re-read and written into a terminal receipt.

## 7. Existing shell, workspace and sandbox inventory

`WorkspaceJail` is a strong data-plane confinement component. It normalizes relative paths,
enforces a server allowlist, rejects absolute/parent/control/hidden/secret paths, verifies the sealed
root digest, uses descriptor-relative `O_NOFOLLOW` reads, limits sizes/counts, and rejects symlink,
hardlink, FIFO, socket and device artifacts. This should form the file-inspection layer of a future
`DisposableWorkspace`.

It is not a process sandbox. The current workspace profile deliberately has zero process and network
capability. The current Dockerfile is a reproducible non-root application runtime, not a general
untrusted-code toolbox. `scripts/b4_network_guard.py` monkeypatches Python sockets during tests; it
does not constrain child processes or non-Python binaries.

The best reusable process example is `RenderStartContractV1Profile` in
`scripts/w4_render_start_profile.py`. It demonstrates fixed argv, private temp cwd, minimal env,
bounded logs, deadline, process-group termination, `/proc` inspection and loopback-only health
checks. It must not be generalized by accepting model-authored command strings. A real initial
`DockerSandboxProvider` must add read-only/ephemeral mounts, non-root uid, network policy, CPU/memory/
PID/time/output bounds, no host socket, no host credential mounts, cleanup and independent receipts.

## 8. Existing patch, test and repair inventory

The W2-W4 implementation is real and reachable, not documentation-only:

- `WorkspacePatchProposalBuilder.build` consumes the exact sealed evidence timeline and one closed
  remediation enum; it generates the diff itself (`workspace/proposal.py:68-292`).
- `canonical_workspace_unified_diff` and proposal validators make before/after content, evidence and
  rollback/verification profiles content-addressed (`workspace/contracts.py:57-598`).
- `WorkspaceAtomicPatchExecutor.apply` takes only `proposal_id`, claims durable ownership, reopens
  the exact root, revalidates hashes, writes a private temporary file, fsyncs, atomically replaces
  one target and emits `PATCH_APPLIED_UNVERIFIED` (`workspace/executor.py:48-280,325-537`).
- `WorkspaceIndependentVerifier.verify` independently scans the full tree, handles crash windows,
  runs only `render_start_contract_v1`, stores a report before a success receipt, and reconciles
  duplicates (`workspace/verifier.py:81-862`).

Limits are intentional: one remediation kind, one `render.yaml` target and one fixed runtime
profile. There is no arbitrary file creation/deletion/rename, multi-file PatchSet, binary edit,
general test discovery or bounded repair loop. Phase 2 must consume these results without widening
the existing W2/W3 tool schemas.

Targeted reachability proof run in Phase 1:

```text
9 passed in 14.09s
```

The nine exact tests covered hero approve/apply/verify/replay, symlink denial, zero-effect proposal,
duplicate apply, fixed runtime token/argv/health/readiness/zero-egress proof, API authority
smuggling, environment sanitization, secret redaction and lost-ACK read-only recovery. No full 1739
test regression was run because Phase 1 changes documentation only and the prompt explicitly
preserves the frozen W7 regression evidence.

## 9. Existing MCP, skills and worker abstractions

### CodingWorker

There is no abstraction that can simply be renamed `CodingWorker`. The nearest reusable shapes are
the frozen runtime dataclasses (`PrimaryAgentRuntime`, `WorkspaceAgentRuntime`,
`WorkspaceAuthorityAgentRuntime`, `WorkspaceVerificationAgentRuntime`) and the dependency-injected
flow services. They carry agent, tools, model provider, session manager and authority references,
but expose task-specific semantics. Phase 2 should add a thin `CodingWorker` protocol/adapter and
compose it with these primitives instead of adding a second orchestration system.

### Event/adapter protocol for Codex App Server

No JSON-RPC/App Server protocol exists. Reusable event material consists of `ControlResult`, UUIDv7
identity, `AuditEvent`, checkpoints, failure taxonomy and Strands `SessionManager`. These can bind a
future adapter's request, streamed events, pause, resume and terminal receipt. Raw App Server events
must be treated as untrusted input and normalized into closed AIOA events before persistence.

### GitHub MCP

No MCP transport or registry exists. The current static tool tuples and explicit
`load_tools_from_directory=False` are valuable safeguards. An official GitHub MCP adapter should be
introduced as a separately filtered, read-only context plane; it must not be merged into the
current mutation tool set and must not inherit execution credentials.

### Skills

No skills/task-pack implementation exists. Later curated packs should be declarative, versioned,
hash-bound inputs that select already-approved capabilities. They must not contain executable
authority, arbitrary shell, secrets or dynamic tool-registration behavior.

## 10. Security gaps proven from source

1. **No process isolation for hostile repositories.** Sealed read confinement exists, but there is
   no disposable executor or kernel-level filesystem/network/resource boundary.
2. **No credential isolation broker.** Sanitized release-child environments exist, but no component
   supplies narrowly scoped GitHub credentials only to a deterministic actuator while proving their
   absence from worker/test processes.
3. **No general safe command contract.** The only strong subprocess implementation has fixed Render
   argv; broadening it without a closed command schema would create arbitrary execution.
4. **No GitHub remote authority binding.** Exact repo/base HEAD/branch/canonical diff/capabilities/
   operation identity and post-write verification are not yet represented for remote state.
5. **No malicious-repository corpus.** Existing tests cover path traversal, links, hidden secrets,
   strict JSON and authority smuggling, but not a complete hostile repo containing instruction files,
   poisoned test output, binary payloads and prompt injection across a coding loop.
6. **Prompt defenses are not a sandbox.** Prompts correctly subordinate the model, but enforceable
   boundaries currently come from fixed tool schemas and deterministic validation; that separation
   must remain true for Codex integration.
7. **Secret scanner packaging is not yet a stable product service.** `scan_files` is reusable but
   lives under `scripts/`; patch/evidence/outbound-payload hooks are not wired into a worker flow.
8. **Python socket guard is process-local.** It cannot prove zero egress for arbitrary binaries or
   child processes. Docker/provider-level network denial is mandatory.
9. **Current hero intelligence is fixed/mock.** `workspace_hero.py:234-279` proves the call path and
   authority model but not a live coding worker or adversarial model behavior.

## 11. Duplicate-implementation risks

The next phases must **not** rebuild or fork:

- capability-to-authority mapping (`nz/authority.py`);
- UUIDv7 and canonical digest utilities (`nz/identifiers.py`, `nz/contracts.py`,
  `workspace/contracts.py`);
- durable human request/decision/nonce/expiry logic (`workspace/authority_contracts.py`,
  `workspace/authority.py`, `workspace/hitl.py`);
- locked integrity-wrapped local authority storage (`workspace/authority_repository.py`,
  `persistence/local_integrity.py`);
- semantic idempotency/effect ownership/replay rules (`persistence/semantic_idempotency.py`,
  `WorkspaceEffectOwnership`);
- sealed-root/path/symlink/hardlink protections (`workspace/fixture.py`, `workspace/jail.py`);
- canonical diff/proposal and exact atomic application (`workspace/proposal.py`,
  `workspace/executor.py`);
- independent read-back, reconciliation and terminal evidence (`workspace/verification_boundary.py`,
  `workspace/verifier.py`, `recovery/coordinator.py`);
- Strands HITL/tool-surface assertions (`agent/factory.py`, workspace agent factories);
- environment sanitization and secret/privacy patterns (`release/preflight.py`,
  `scripts/phase3/scan_secrets.py`, `scripts/scan_public_submission.py`);
- current AWS provider and remediation boundaries.

A new adapter may compose these components, but must not create a parallel approval database,
parallel event ledger, parallel hash format, model-controlled Git wrapper or a second success state.

## 12. Proposed Phase 2 entry points

Phase 2 should remain a narrow Codex worker/App Server integration and use these exact extension
points:

1. Add a small coding-worker protocol adjacent to `src/aioa_cloudops_agent/agent/`, modeled after
   the existing runtime dataclasses but returning `ControlResult` and normalized events. Do not
   modify frozen CloudOps tool tuples.
2. Reuse `domain/models.py:ExecutionContext`, `nz/identifiers.py`, the failure taxonomy,
   `persistence/models.py:Checkpoint` and audit-event contracts for worker-run identity and state.
3. Add an App Server adapter that owns transport only. Normalize every inbound event into closed
   Pydantic contracts before it reaches persistence or policy. Model text remains data.
4. Reuse `WorkspaceRef`, `MaterializedWorkspace` and root/artifact digests as the worker workspace
   identity. For Phase 2, keep the worker non-applying and do not claim a sandbox until a real
   provider exists.
5. Feed candidate edits into a generalized descendant of `WorkspacePatchProposal`; keep canonical
   before/after content and diff SHA-256, evidence digest, expiry and verification profile bindings.
6. Persist worker events through the existing repository/audit abstractions. Do not let the App
   Server adapter write terminal authority directly.
7. Add contract tests with a fake App Server transport first: malformed/duplicate/out-of-order
   events, injected instructions, cancellation, timeout, resume, output cap and secret-shaped output.
8. Keep GitHub MCP, Docker execution, installers and remote writes out of Phase 2 unless a later
   phase prompt explicitly authorizes them.

Future phases should place `DockerSandboxProvider` behind the workspace identity boundary, the
read-only GitHub MCP behind a filtered context adapter, and `GitHubWriteActuator` behind
`WorkspaceAuthorityService`-style exact approval plus durable effect ownership.

## 13. Minimal dependency plan

No dependency was installed in Phase 1.

- Phase 2 should first use the existing `pydantic`, Strands and standard-library process/JSON/async
  facilities. A new dependency is justified only if the selected Codex App Server protocol cannot
  be implemented or tested safely without its official SDK.
- DockerSandboxProvider should initially use a fixed external Docker/Podman CLI adapter with
  structured argv, not add a large SDK automatically.
- Official GitHub MCP should remain an external pinned executable/container; no Python MCP package
  should be added until transport/version requirements are proven.
- A GitHub write client choice must be deferred until the exact REST operations and credential model
  are specified. Do not add both a GitHub SDK and `gh` wrapper.
- Continue exact pins/hashes and clean-room builds for any approved addition.

## 14. Open questions and blockers

- The repository does not pin or document a Codex App Server protocol/version. Phase 2 must obtain
  and freeze that contract before implementation; no network lookup was authorized in Phase 1.
- The official GitHub MCP transport/image/version and its deterministic read-only tool allowlist are
  unresolved and correctly deferred.
- The future GitHub credential model (fine-grained PAT now, GitHub App later) has no repository
  contract yet. Credential custody must be designed before remote integration.
- No sandbox engine capability probe establishes what is available in production hosts. The current
  B5 build engine proves release reproducibility, not safe hostile-code execution.
- Multi-file patch semantics, file creation/deletion policy, binary denial and maximum PatchSet size
  require explicit future decisions.
- Remote divergence, branch protection, Actions status and PR postcondition tests require later
  credentialed integration fixtures; they cannot be proven locally in Phase 1.
- Preserved deployment stashes remain outside W7A scope and must not be auto-applied.

None of these blocks a non-applying, local, fake-transport-first Phase 2 adapter. They do block any
claim of live GitHub, sandboxed code execution or deterministic remote write readiness.

## 15. Final Phase 2 go/no-go gate

**GO — with the Phase 2 boundary kept narrow.**

Phase 2 is ready to implement only the Codex worker/App Server adapter contracts and local tests,
while reusing current identity, failure, checkpoint, audit and authority primitives. Phase 2 is not
authorization for MCP, Docker sandbox execution, package installation, GitHub credentials, GitHub
writes, AWS, deployment or W8.

Acceptance facts for this Phase 1 audit:

```text
FROZEN_W7_HEAD_VERIFIED=945c87052815b237004d259fe993cc92cbd579b7
W7_B5_B6_MODIFIED=NO
W8_EXECUTED=NO
AWS_CALLS=0
DEPLOYMENTS=0
REMOTE_PUSHES=0
EXECUTABLE_CODE_CHANGED=NO
DISCOVERY_DOMAINS=15/15
PRESENT=3
PARTIAL=9
MISSING=3
CONFLICTING=0
TARGETED_REACHABILITY_TESTS=9/9 PASS
PHASE_2_READY=YES
```

The required next step is `W7A_PHASE_2_CODEX_WORKER_APP_SERVER_INTEGRATION`. This document grants no
authority to begin it automatically.

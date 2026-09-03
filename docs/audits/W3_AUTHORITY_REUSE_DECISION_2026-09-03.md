# W3 authority reuse decision — 2026-09-03

## Decision

W3 reuses the existing AIOA authority model and durable-storage discipline without mapping a
workspace patch into the CloudOps `STOP_SANDBOX_INSTANCE` domain. The workspace path remains an
additive adapter under `aioa_cloudops_agent.workspace`; the canonical CloudOps five-tool runtime,
proposal schema, approval payload, durable flow, and local execution flow remain unchanged.

This is one approval philosophy with two deliberately typed domain adapters:

```text
durable exact proposal
  -> human-visible payload derived from durable truth
  -> canonical request hash
  -> actor-session + one-time decision nonce
  -> decision persisted before native resume/effect
  -> duplicate reconciliation or conflict rejection
  -> effect ownership persisted before effect
```

Workspace data is never coerced into `ActionTarget`, EC2 instance state, AWS capability, or a
`STOP_SANDBOX_INSTANCE` approval.

## Existing classes and functions reused

- `ApprovalDecision`, `AuthorityGate`, `NonZeroContract`, `Sha256Digest`, and
  `Uuid7Identifier` retain their canonical Non-Zero meanings.
- `WorkspacePatchProposal`, `WorkspaceRef`, and `canonical_workspace_json_digest` remain the W2
  source of proposal identity and canonical hashing.
- `validate_local_path`, `locked_private_file`, `read_private_json`,
  `seal_local_payload`, `open_local_payload`, and `atomic_write_private_json` provide the same
  owner-only, integrity-sealed, locked, fsync-and-replace persistence discipline used by the
  existing local durable store.
- Native Strands `HumanInTheLoop`, `Confirm`, and `Deny` retain the existing pre-dispatch
  confirmation mechanism and default-deny posture.
- The ordering and conflict principles of `DurableProposalHumanInTheLoop`,
  `DurableApprovalFlow`, and `LocalHitlExecutionFlow` are reused semantically: proposal first,
  interrupt/checkpoint before caller return, exact resume binding, decision before native resume,
  and effect ownership before effect.

No existing helper is extracted or generalized in W3. This avoids changing byte or behavior in
the certified CloudOps authority path merely to share small pieces of code.

## CloudOps files modified

None are planned or required. In particular, W3 does not modify:

- `src/aioa_cloudops_agent/agent/hitl.py`
- `src/aioa_cloudops_agent/agent/approval_flow.py`
- `src/aioa_cloudops_agent/agent/local_hitl.py`
- `src/aioa_cloudops_agent/agent/factory.py`
- CloudOps proposal, approval, execution, persistence, or recovery contracts

Historical CloudOps semantics therefore remain unchanged. The full regression, P0, P1, B4, and
focused replay/recovery baselines will provide the compatibility proof.

## Workspace-specific types

W3 introduces strict workspace-domain records for:

- proposal state and the durable W2 proposal record;
- the exact human-visible patch approval payload and canonical request hash;
- approval interrupt/checkpoint and typed resume request;
- durable human decision;
- effect/idempotency ownership;
- atomic patch-apply receipt and reconciliation marker;
- a versioned workspace authority repository; and
- workspace-native HITL plus the proposal-id-only apply boundary.

These records name `run_id`, `trace_id`, `workspace_id`, fixture, root, target, patch, evidence,
verification profile, and rollback facts directly. They cannot accept a replacement path,
content, diff, command, cwd, environment, verifier, provider, or deployment parameter.

## Equivalent binding and replay semantics

- **Actor session:** every external decision is bound to a validated `actor_session_id`; the
  exact value is stored in the durable decision before native resume or file effect.
- **Nonce:** the decision carries one bounded `decision_nonce`; an identical decision may
  reconcile, while a changed nonce or conflicting decision is rejected. The nonce is authority
  data, never model output.
- **Request hash:** canonical JSON of the complete durable-proposal-derived approval payload is
  SHA-256 hashed. Display wrapping or translated explanatory text is outside that identity.
- **Replay:** proposal, interrupt, request, run, workspace, fixture, base, target-before, after,
  patch, evidence, support, version, expiry, and verification-profile identities must match the
  durable record. Cross-run, cross-workspace, stale, expired, or drifted submissions fail closed.
- **Conflict:** the first durable decision and first effect ownership win. Exact duplicates return
  the same durable truth without a second write; changed decisions or identities fail closed.
- **Ordering:** approval request/interrupt is durable before it is returned; a human decision is
  durable before native Strands resume; `APPLYING` ownership is durable before `os.replace`; the
  apply receipt is durable after the observed atomic effect.

This preserves the existing Non-Zero authority semantics while keeping CloudOps and workspace
facts honest, narrow, and independently typed.

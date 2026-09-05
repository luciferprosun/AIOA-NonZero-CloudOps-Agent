# W7A Phase 7 — Canonical Execution Capsule

Date: 2026-09-05 Europe/Berlin

Work branch: `codex/w7a-agent-execution-slice`

Entry head: `dc38cf2b1ae97b5986bc0a3c496a16994ba5d4e7`

Frozen W7/B5/B6 head: `945c87052815b237004d259fe993cc92cbd579b7`

## Result

Phase 7 is **PASS**. The canonical `ExecutionCapsule` composes the existing
Phase 5 actual-state `PatchSet`, Phase 6 ordered V0–V6 receipts, Phase 4 Docker
sandbox identity, normalized GitHub repository/base/target identity, the closed
future operation sequence, credential classes, and one exact human approval
request into a strict immutable self-hashed contract.

The capsule is an envelope, not an executor. Its `mutation_authority`,
`github_authority`, `aws_authority` and `execution_engine` fields are fixed to
false. It has no shell, Git argv, token, arbitrary remote URL, dynamic tool,
model-authored policy or execution method.

## Reuse and authority boundary

- Strict frozen Pydantic behavior comes from `NonZeroContract`.
- UUIDv7 and SHA-256 aliases come from `aioa_cloudops_agent.nz`.
- Canonical hashing reuses `canonical_workspace_json_digest`.
- Repository source truth reuses the Phase 3 `GitHubRepositoryIdentity` and is
  case-normalized before entering the capsule.
- Changed files and base identity come only from the validated Phase 5
  `PatchSet`; worker narration is never read.
- Ordered receipts and review/policy/secret/cleanup facts come only from a
  terminal PASS `RepairLoopResult`.
- Worker, sandbox and test credential classes are fixed to `NONE`; only the
  later deterministic actuator may briefly receive a separately supplied write
  credential.
- Human authority remains separate. An exact self-hashed decision must match
  capsule SHA, request SHA, request ID, actor, nonce hash and expiry before
  `ExecutionAuthorityReceipt` can exist.

The decision validator rejects absence, denial, expiry, actor/nonce/request or
capsule mismatch and replay of a completed operation. Its receipt explicitly
states `remote_effect_completed=false`; approval validation is not remote-write
success.

## Adversarial proof

The required tests prove stable repeated canonicalization, strict extra-field
denial, repository normalization, default/ref-alias denial, base/head/PatchSet/
sandbox tamper detection, authority-text injection denial, duplicate/reordered
V0–V6 event denial, missing/expired/denied/wrong actor/wrong nonce/wrong request
approval denial, replay denial, nonce non-retention and the absence of GitHub
write methods from the read-only MCP and `SandboxProvider` interfaces.

The machine evidence contains a deterministic synthetic cross-phase fixture so
reviewers can validate the capsule schema and hash. It is explicitly marked
`synthetic_contract_fixture_only=true` and `human_approval_bound=false`; it is
not a live Phase 8 approval or product mutation.

```text
PHASE_4_RESULT=PASS
PHASE_5_RESULT=PASS
PHASE_6_RESULT=PASS
PHASE_7_FOCUSED=29/29 PASS
CAPSULE_SHA256=9d052d8c3a1c314b9da46f827d112ab8d1c6867dc951c35cf54e9508b65bea1b
SCHEMA_STRICT_EXTRA_FORBID=PASS
TAMPER_MATRIX=PASS
REPLAY_DENIAL=PASS
WORKER_GITHUB_WRITE_CREDENTIALS=0
SANDBOX_GITHUB_WRITE_CREDENTIALS=0
PRODUCT_RUNTIME_GITHUB_WRITES=0
AWS_CALLS=0
AWS_MUTATIONS=0
DEPLOYMENTS=0
RUFF=PASS
SECRET_SCAN=PASS
GIT_DIFF_CHECK=PASS
PHASE_7_RESULT=PASS
```

Evidence: `docs/evidence/w7a/phase7-execution-capsule.json`.

No frozen W7/B5/B6 evidence, default branch, tag, release, AWS resource or
deployment was changed. A normal development-branch checkpoint push is the
only remote action authorized by this Phase 7 closure.

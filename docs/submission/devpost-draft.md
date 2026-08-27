# Devpost Draft — AIOA Non-Zero CloudOps Agent

Status: audited `DEPLOYMENT_READY_LOCAL_RC` draft for owner review; not externally submitted.

## One-line pitch

A human-authorized CloudOps agent that cannot turn a model suggestion into success until the exact
action is approved, executed once, and independently verified with durable evidence.

## The problem

Professional agents are useful only when people can trust what they observed, what they proposed,
who authorized it, whether it ran more than once, and whether the claimed outcome really happened.
Cloud automation often collapses those questions into one optimistic “success” response. That is
especially risky for remediation actions.

## What we built

AIOA Non-Zero CloudOps is one Strands agent surrounded by a deterministic authority and evidence
plane. Its bounded AWS deployment design can inspect one allow-listed sandbox EC2 instance, evaluate
utilization, create remediation evidence, pause for exact human approval, call a separately
permissioned private stop executor, and verify the observed state independently. In Phase 3 this AWS
path is a validated SAM/CloudFormation deployment candidate, not a deployed service.

The credential-free Local-First implementation makes the safety properties reviewable without cloud
access. Deterministic AWS-shaped fixtures cover an unattached Elastic IP, unsafe Security Group
ingress, missing tags, and a compliant instance. The runtime creates inert proposals, binds approve
or deny to exact evidence and a one-time challenge, executes one approved mock action, recovers a
pending approval after restart, rejects conflicting replay, reconciles after interruption, and
reaches `SUCCESS_WITH_EVIDENCE` only after independent read-back.

## How humans stay in control

- The model can propose; it cannot grant authority.
- `AUTO`, `PLAN_AND_CONFIRM`, and `NEVER_AUTONOMOUS` are deterministic policy classes.
- Approval binds the run, proposal ID/hash, evidence hash, version, expiry, actor session, request,
  nonce hash, and decision hash.
- Denial is terminal and cannot call the executor.
- Approval and execution are separate gestures and durable states.
- Execution ownership is persisted before the side effect; identical retries reconcile, while
  changed replays fail closed.
- A provider acknowledgement is not success. Independent verification evidence is required.

## Demo

The primary jury command is entirely local and labels itself `MOCK_OFFLINE_NEVER_LIVE`. In one
machine-readable receipt it proves the approve, deny, replay, restart recovery, terminal
reconciliation, and five fail-closed paths. It records one approved mock mutation, zero denied/replay/
recovery mutations, zero external connections, zero AWS mutations, and zero live receipts. The
optional operator console binds only to `127.0.0.1`, uses an owner-only token file and same-origin UI,
and stores no token in browser storage.

## Technology

- Python 3.12 and strict Pydantic contracts;
- Strands Agents SDK with OpenTelemetry support;
- Amazon Bedrock / Nova 2 as the pinned future model platform;
- provider-neutral cloud and model adapters;
- a retained, on-demand DynamoDB design for durable truth;
- an operator-supplied private S3 bucket contract for future deployment artifacts;
- atomic local JSON persistence for credential-free execution;
- one AWS SAM/CloudFormation path with separated orchestrator and private executor IAM; and
- executable P0/P1 safety gates plus deterministic claim-to-proof evidence.

No sentence above claims that DynamoDB, S3, Bedrock, Lambda, or the API is currently live.

## What is distinctive

The product is intentionally “Non-Zero”: missing evidence, ambiguous provider results, stale
approvals, replay conflicts, dependency outages, recovery uncertainty, and verification mismatch are
explicit states rather than accidental success. Consequential authority stays in deterministic
application code instead of model output.

## Accomplishments proven locally

- one canonical run/checkpoint lifecycle from investigation through verified completion;
- an exact five-tool single-agent surface with unknown capability default deny;
- durable human-in-the-loop approval and restart recovery;
- private, narrowly scoped future execution boundary with emergency vetoes;
- protected mock execution for exact EIP release and ingress revocation;
- authenticated loopback API and embedded operator console;
- a classified deployment contract, offline preflight fixtures, 22-resource IaC manifest,
  ownership-bound cleanup plan, post-deploy verifier contract, and commit-bound RC attestation; and
- deterministic full-suite, P0/P1, API, replay, recovery, verification, secret-scan, and package
  proofs.

## Challenges and lessons

The hardest part was preserving authority and truth across every crash window. Approval must survive
a restart without becoming transferable. An execution receipt must survive when a workflow
checkpoint does not. Verification must be independent of the executor's optimistic response. Those
constraints shaped the data model and made the agent safer and more explainable.

## Evidence map

| Claim | Local evidence |
|---|---|
| Exact human authority and default deny | `scripts/run_p0_gate.py`; `scripts/run_p1_gate.py`; policy and HITL tests |
| Approve = one mock mutation + independent evidence | `scripts/phase3/run_jury_demo.py`; `docs/evidence/release/phase3-offline-verifier-receipt.json` |
| Deny, replay, and recovery add zero mutation | Same jury/verifier receipt; Phase 3 verifier and demo tests |
| Offline path opens no socket and makes no AWS mutation | `test_phase3_*` socket guards; hashed local-gate evidence |
| Deployment surface and IAM separation | `requirements/phase3-deployment-contract.json`; `infra/sam/template.yaml`; 22-resource expected manifest |
| Cleanup requires proven ownership and fresh approval | `requirements/phase3-cleanup-contract.json`; `docs/operations/phase3-rollback-cleanup.md` |
| RC bytes and commit are bound fail-closed | `.local/phase3/rc-attestation.json` after final push; attestation schema/tests |
| Historical product claims remain mock/live typed | `docs/evidence/reviewer-evidence-manifest.json`; its validator |

The `.local` gate and attestation receipts are deliberately untracked operator evidence. The committed
Phase 3 gate report records their safe hashes and results without publishing host-specific or secret
material.

## Current limitations and next steps

No AWS infrastructure or live mutation has been performed by this project. Live deployment remains
blocked until an authorized operator supplies and validates the intended account/role, region,
private artifact bucket, pre-existing sandbox binding, judge-secret authority, CloudWatch history,
Nova 2 access, budget owner, reviewed change set, and explicit deploy approval. The local preflight
engine represents each unavailable check as `NOT_RUN_EXTERNAL` or `BLOCKED_EXTERNAL`; it never
converts absence into PASS.

After those prerequisites, the smallest safe sequence is read-only preflight, human review of its
receipt, explicit approval of the exact change set, deployment, live post-deploy verification, receipt
review, and owner-controlled Devpost submission. AgentCore remains an optional future evaluation,
not a dependency of the proven architecture.

## Placeholders that require future live evidence

Do not promote these placeholders into submission claims until the named receipt exists:

- `[LIVE_DEPLOYMENT_RECEIPT_REQUIRED: exact stack ID/hash, account/region binding, deployed SHA]`;
- `[LIVE_IAM_SIMULATION_REQUIRED: effective read/write separation in the authorized account]`;
- `[LIVE_BEDROCK_RECEIPT_REQUIRED: authorized Nova 2 invocation and model identifier]`;
- `[LIVE_REMEDIATION_RECEIPT_REQUIRED: approved sandbox-only mutation plus independent read-back]`;
- `[LIVE_ROLLBACK_RECEIPT_REQUIRED: ownership-checked residual-resource verification]`; and
- `[DEVPOST_SUBMISSION_RECEIPT_REQUIRED: owner submission URL/timestamp]`.

## Repository proof commands

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/run_p0_gate.py
.venv/bin/python scripts/run_p1_gate.py
.venv/bin/python scripts/phase3/scan_secrets.py
.venv/bin/python scripts/phase3/run_post_deploy_verifier.py --check
.venv/bin/python scripts/phase3/run_jury_demo.py
```

This draft makes no claim of external submission, deployed availability, effective live IAM, live
Bedrock use, a real AWS mutation, or a live verification receipt.

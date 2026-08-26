# Devpost Draft — AIOA Non-Zero CloudOps Agent

Status: local draft prepared for owner review; not externally submitted.

## One-line pitch

A human-authorized CloudOps agent that cannot turn a model suggestion into success until the exact
action is approved, executed once, and independently verified with durable evidence.

## The problem

Professional agents are useful only when people can trust what they observed, what they proposed,
who authorized it, whether it ran more than once, and whether the claimed outcome really happened.
Cloud automation often collapses those questions into one optimistic “success” response. That is
especially risky for remediation actions.

## What we built

AIOA Non-Zero CloudOps is a single Strands agent surrounded by a deterministic control plane. Its
canonical bounded AWS workflow inspects one allow-listed sandbox EC2 instance, evaluates utilization,
builds remediation evidence, requests human approval for an exact stop proposal, executes through a
private scoped boundary, and verifies the observed state independently.

The credential-free Local-First path makes those safety properties fully reviewable without cloud
access. It includes deterministic AWS-shaped fixtures for an unattached Elastic IP, unsafe Security
Group ingress, missing tags, and a compliant instance. It produces exact inert proposals, binds an
authenticated human approve/deny decision to the evidence and a one-time challenge, executes only an
approved mock action, reconciles after interruption without replaying the mutation, and reaches
`SUCCESS_WITH_EVIDENCE` only after independent read-back.

## How humans stay in control

- The model can propose; it cannot grant authority.
- `AUTO`, `PLAN_AND_CONFIRM`, and `NEVER_AUTONOMOUS` are deterministic policy classes.
- Approval binds the run, proposal ID/hash, evidence hash, version, expiry, actor session, request,
  nonce hash, and decision hash.
- Denial is terminal and cannot call the executor.
- Approval and execution are separate gestures and durable states.
- Execution ownership is written before the side effect; identical retries reconcile, while changed
  replays fail closed.
- A provider acknowledgement is never called success. Independent verification evidence is required.

## Demo

The local operator console runs only on `127.0.0.1`, uses an owner-only token file and a same-origin UI,
and stores no token in browser storage. A reviewer can inspect an exact proposal, approve or deny it,
resume execution, see the receipt and verification, and retry safely. The deterministic CLI demo
also prints the evidence/proposal/receipt/verification hashes and proves zero network calls.

## Technology

- Python 3.12 and strict Pydantic contracts
- Strands Agents SDK with OpenTelemetry support
- Amazon Bedrock / Nova 2 as the pinned planned model platform
- provider-neutral cloud and model adapters
- DynamoDB and S3 deployment contracts for durable truth and evidence
- atomic local JSON persistence for credential-free execution
- AWS SAM/CloudFormation deployment candidate with separated orchestrator and private executor IAM
- executable P0/P1 safety gates and a deterministic claim-to-proof reviewer manifest

## What is distinctive

The product is intentionally “Non-Zero”: missing evidence, ambiguous provider results, stale
approvals, replay conflicts, dependency outages, recovery uncertainty, and verification mismatch are
explicit states rather than accidental success. The demo is not a permissive chatbot wrapped around
cloud credentials; consequential authority stays in deterministic application code.

## Accomplishments

- one canonical run/checkpoint lifecycle from investigation through verified completion;
- exact five-tool single-agent surface with unknown capability default deny;
- durable human-in-the-loop approval and restart recovery;
- private, narrowly scoped execution boundary with emergency vetoes;
- protected Local-2 mock executor for exact EIP release and ingress revocation;
- authenticated loopback API and embedded operator console;
- deterministic clean-clone, P0, P1, API, replay, recovery, and verification proofs;
- reviewer evidence manifest that never upgrades mocked evidence into a live claim.

## Challenges and lessons

The hardest part was not generating an action; it was preserving authority and truth across every
crash window. Approval must survive a restart without becoming transferable. An execution receipt
must survive when the workflow checkpoint does not. Verification must be independent of the
executor's optimistic response. Those constraints shaped the data model and made the agent safer and
more explainable.

## Current limitations and next steps

No AWS infrastructure or live mutation has been performed by this project. Live deployment remains
blocked until an authorized operator binds the correct hackathon account/role, private artifact
bucket, reviewed change set and IAM acknowledgement, dedicated judge secret, exact pre-existing
sandbox, sufficient CloudWatch history, Nova 2 access, and budget-notification owner. After those
prerequisites, the same adapter contracts can be connected to live reads and the already private
executor without weakening human authority. AgentCore remains an optional later decision, not a
dependency of the proven workflow.

## Repository proof commands

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/run_p0_gate.py
.venv/bin/python scripts/run_p1_gate.py
.venv/bin/python scripts/validate_reviewer_evidence_manifest.py
```

This draft makes no claim of external submission, deployed availability, effective live IAM, or a
real AWS mutation receipt.

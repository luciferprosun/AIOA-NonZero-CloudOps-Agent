# Devpost Draft — AIOA Non-Zero CloudOps Agent

Status: audited `DEPLOYMENT_READY_LOCAL_RC` plus W5 local judge-hero checkpoint; historical B6
candidate predates W5 and must be recertified before publication; not externally submitted.

## One-line pitch

A human-authorized Strands CloudOps agent that cannot convert a model suggestion into success until
the exact action is approved, executed once, and independently verified with durable evidence.

## The problem

Professional agents become risky when investigation, authority, execution, and success are collapsed
into one optimistic answer. Operators need automation that makes uncertainty visible and preserves
the human's control across retries and restarts. Cloud remediation is especially sensitive because
an unverified acknowledgement or duplicate retry can hide a consequential failure.

## What we built

AIOA Non-Zero CloudOps uses one Strands agent and five bounded tools to investigate an AWS-shaped
resource, gather evidence, and create an inert remediation proposal. Deterministic Non-Zero code
binds approve or deny to that exact evidence, proposal, actor session, expiry, and one-time
challenge. Approval may execute one allow-listed mock action. Denial executes nothing. Independent
read-back—not the provider's acknowledgement—determines whether the run reaches
`SUCCESS_WITH_EVIDENCE`.

The credential-free portable implementation proves pending-approval recovery after restart,
interrupted-execution reconciliation, replay rejection, resource-binding rejection, and five
fail-closed safety probes. Its default model and cloud adapters are deterministic local mocks, so
the full judge path requires neither credentials nor network access. The bounded AWS deployment
design remains a validated future path, not a deployed service.

The featured W5 experience applies the same rules to one failed-deployment story. A Strands agent
reads a sealed, sanitized evidence set and diagnoses an exit `127` / `File name too long` failure.
Trusted code—not model prose—builds one exact `render.yaml` diff. The judge can approve or deny the
hash-bound request, see an approved patch stop as unverified, invoke independent startup proof, and
then test that the consumed approval cannot produce a second effect.

## How humans stay in control

- The model can propose; it cannot grant authority.
- Approval binds the run, proposal, evidence, actor session, expiry, and one-time challenge.
- Denial is terminal and cannot call the executor.
- Approval and execution are separate gestures and durable states.
- Execution ownership is persisted before the side effect.
- Identical retries reconcile, while changed replays fail closed.
- A provider acknowledgement is not success. Independent verification evidence is required.

## Demo

The primary local judge story is **Fix a Failed Deployment Safely**:

```text
Observe -> Evidence -> Root Cause -> Exact Patch -> Policy -> Human Decision
        -> Execute Once -> Independent Verify -> Receipt -> Replay Rejected
```

The approve scenario performs exactly one private-workspace `render.yaml` replacement, remains at
`PATCH_APPLIED_UNVERIFIED` until the independent W4 proof passes, and then records
`SUCCESS_WITH_EVIDENCE`. The deny scenario is terminal and performs zero mutation. Refresh restores
durable authority state; replay reconciles the consumed approval with zero additional mutation and
zero additional process/profile execution. The older AWS-shaped CloudOps mock stories remain
available as regression demonstrations.

The receipt also records zero external network connections, zero AWS calls, and zero AWS mutations.
The optional browser console makes the same authority and evidence stages visible while remaining
authenticated and loopback-only. It stores no authentication token in browser storage.

## Technology

- Python 3.12 and strict Pydantic contracts;
- the Strands Agents SDK with a deterministic mock model by default;
- durable human-in-the-loop state, nonce consumption, and semantic idempotency;
- provider-neutral model and cloud adapters;
- atomic local JSON persistence for the credential-free flow;
- independent verification and hash-bound JSON evidence;
- an authenticated loopback-only operator console; and
- a non-root, digest-pinned, hash-locked OCI container.

The workspace hero uses staged four-, five-, six-, and seven-tool profiles for W1 evidence, W2
proposal, W3 human-bound apply, and W4 proposal-ID-only verification. No generic shell, file-write,
package, Git, browser/MCP, URL-fetch, provider, or deployment capability is exposed to the model or
browser.

Amazon Bedrock and bounded AWS adapters remain optional. They are not required by the portable
critical path and were not invoked for this candidate. No sentence above claims that DynamoDB, S3,
Bedrock, Lambda, or an API is currently live.

## What is distinctive

The model can propose but cannot grant authority. A provider response cannot grant success. A retry
cannot silently become a second effect. Missing evidence, ambiguous recovery, stale approval,
dependency failure, binding mismatch, and verification mismatch are modeled outcomes that fail
closed. Consequential authority stays in deterministic application code instead of model output.

## Accomplishments proven locally

- one canonical run and checkpoint lifecycle from investigation through verified completion;
- an exact five-tool single-agent surface with unknown capability default deny;
- durable evidence-bound human approval, terminal denial, and restart recovery;
- protected mock execution with independent verification;
- authenticated loopback API and embedded operator console;
- a locally certified non-root OCI runtime with a read-only root filesystem, dropped capabilities,
  and no-new-privileges;
- executable P0/P1, reliability, security, privacy, and reproducibility gates; and
- deterministic public-tree inventory, exclusions, checksums, and claim-to-proof mapping.

## Challenges and lessons

The difficult edge is the crash window around a consequential effect. Approval has to survive a
restart without becoming transferable. An uncertain effect must reconcile before retry. A provider
receipt must not substitute for independent verification. Those constraints required separate
authority, execution, and truth planes. They also reinforced a broader lesson: useful agents need
deterministic safety boundaries around probabilistic reasoning.

## Evidence map

| Claim | Local evidence |
|---|---|
| Exact human authority and default deny | `scripts/run_p0_gate.py`; `scripts/run_p1_gate.py`; policy and HITL tests |
| Approve = one mock mutation plus independent evidence | `python -m aioa_cloudops_agent.portable`; portable sandbox tests; B5 container-gate receipt |
| Deny, replay, and recovery add zero mutation | Portable receipt fields; recovery and reconciliation tests |
| Offline path opens no external socket and makes no AWS call | Portable socket guards; B5 container-gate receipt |
| One Strands agent exposes five bounded tools | Strands agent tests; provider-neutral compatibility tests |
| Container runtime is non-root and hardened | `Dockerfile`; B5 non-root and image-privacy receipts |
| Public export is deterministic and sanitized | `PUBLICATION_MANIFEST.json`; `SHA256SUMS`; B6 clean-room report |
| Historical product claims remain mock/live typed | `docs/evidence/reviewer-evidence-manifest.json`; its validator |

The committed B5 artifacts bind the exact source, dependency inputs, image identity, runtime checks,
and portable receipt hashes without publishing host-specific or secret material. The public archive
adds a complete inventory, explicit exclusions, file checksums, a privacy-scan receipt, and the B6
clean-room report.

## Current limitations and next steps

No AWS infrastructure or live mutation has been performed by this project. W5 is a locally
certified source-checkout hero, not a production deployment or current publication candidate. No
public endpoint, registry push, live AWS identity, live Bedrock inference, effective deployed IAM,
real cloud mutation, video publication, or Devpost submission is claimed. Historical B5/B6 receipts
do not cover W5 runtime/UI changes; a final RC recertification is required before release. The
optional AWS path requires a separate authorized live-demo phase and new receipts.

The next engineering step is a separately audited W6 security/feature freeze, followed later by
final RC B5/B6 recertification. Any future live phase must begin with read-only preflight, explicit
scope and account approval, reviewed change set, bounded deployment, independent post-deploy
verification, and owner-controlled submission. Missing external evidence remains blocked or not
run; it never becomes a local PASS.

## Placeholders that require future live evidence

Do not promote these placeholders into submission claims until the named receipt exists:

- `[LIVE_DEPLOYMENT_RECEIPT_REQUIRED: exact stack ID/hash, account/region binding, deployed SHA]`;
- `[LIVE_IAM_SIMULATION_REQUIRED: effective read/write separation in the authorized account]`;
- `[LIVE_BEDROCK_RECEIPT_REQUIRED: authorized model invocation and model identifier]`;
- `[LIVE_REMEDIATION_RECEIPT_REQUIRED: approved sandbox-only mutation plus independent read-back]`;
- `[LIVE_ROLLBACK_RECEIPT_REQUIRED: ownership-checked residual-resource verification]`; and
- `[DEVPOST_SUBMISSION_RECEIPT_REQUIRED: owner submission URL/timestamp]`.

## Repository proof commands

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/run_p0_gate.py
.venv/bin/python scripts/run_p1_gate.py
.venv/bin/python scripts/phase3/scan_secrets.py
B6_SOURCE="$(git rev-parse HEAD)"
test -z "$(git status --porcelain)"
test "${#B6_SOURCE}" -eq 40
python scripts/build_public_submission.py --source-ref "$B6_SOURCE" --output-root <empty-directory>
python scripts/scan_public_submission.py --root <candidate-directory>
```

This draft makes no claim of external submission, deployed availability, effective live IAM, live
Bedrock use, a real AWS mutation, or a live verification receipt.

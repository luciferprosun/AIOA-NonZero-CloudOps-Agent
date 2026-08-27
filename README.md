# AIOA Non-Zero CloudOps — Bounded Idle EC2 Remediation Agent

Newly authored work for the **AWS Agents for Humans Hackathon 2026**.

- Track: Professional Agents
- Status: Phase 3 `DEPLOYMENT_READY_LOCAL_RC` candidate with a frozen deployment contract, offline preflight/IaC/cleanup/verifier proofs, hardened jury demo, and commit-bound attestation; no live deployment or AWS mutation has run
- Orchestration: one Strands Agent
- Model platform: Amazon Bedrock
- Current capability: five bounded tools covering investigation, proposal-bound stop, and independent verification
- Safety boundary: executable P0/P1 matrices, bounded dependency circuits, deterministic reviewer evidence, and an independent fail-closed emergency veto immediately around the private mutation boundary

## Non-Zero Principle

No silent, ambiguous, untraceable, unverifiable, or falsely-successful state may pass as a valid result.

This repository contains newly authored hackathon work. Existing AIOA, AOIA, and Non-Zero projects are prior art; no implementation code from them has been imported.

No AWS infrastructure has been deployed by this project. A private, tightly scoped stop executor is
implemented but defaults disabled and has not been invoked against live EC2. A truthful local Devpost
draft and demo runbook are prepared, but no external submission has been made. “Release candidate”
means deployment-ready from local evidence; it does not mean production deployed or live verified.

## Local quickstart

Prerequisites are Git, Python 3.12+ with virtual-environment support, and network access only for cloning and installing declared dependencies. No AWS credentials are required; AWS writes remain disabled.

```bash
git clone https://github.com/luciferprosun/AIOA-NonZero-CloudOps-Agent.git
cd AIOA-NonZero-CloudOps-Agent
python3.12 -m venv .venv
.venv/bin/python -m pip install ".[dev]"
.venv/bin/python -m pytest -q
.venv/bin/python scripts/run_p0_gate.py
.venv/bin/python scripts/run_p1_gate.py
.venv/bin/python scripts/build_reviewer_evidence_manifest.py --check
.venv/bin/python scripts/validate_reviewer_evidence_manifest.py
```

The P1 runner includes the clean-clone proof. To run only that reproducibility check:

```bash
.venv/bin/python scripts/prove_clean_clone.py --mode auto
```

The harness creates another disposable environment with `python -m venv`. On hosts where the standard-library module lacks `ensurepip`, the declared dev dependency provides the documented `python -m virtualenv` fallback. These checks use mocks and static proof. They do not deploy infrastructure or call live AWS services.

Phase 3 adds local release validation without requiring AWS credentials:

```bash
.venv/bin/python scripts/phase3/build_deployment_contract.py --check --json
.venv/bin/python scripts/phase3/validate_iac.py --check
.venv/bin/python scripts/phase3/build_cleanup_contract.py --check
.venv/bin/python scripts/phase3/run_post_deploy_verifier.py --check
.venv/bin/python scripts/phase3/scan_secrets.py
.venv/bin/python scripts/phase3/run_jury_demo.py
```

After committing all intended files, the all-in-one final gate binds its evidence to that clean SHA:

```bash
HEAD_SHA="$(git rev-parse HEAD)"
.venv/bin/python scripts/phase3/run_local_gate.py --expected-head "$HEAD_SHA"
```

The gate executes the complete suite once, P0/P1, Ruff, dependency and package checks, generated
artifact checks, secret scanning, no-socket tests, verifier, and the approve/deny/replay/recovery jury
path. Its receipts are private files under `.local/phase3/`; the committed gate report publishes only
safe results and hashes.

The deterministic claim-to-proof index is in [`docs/evidence/`](docs/evidence/). The canonical Phase 3
architecture is [`docs/architecture/phase3-deployment-ready-local-rc.md`](docs/architecture/phase3-deployment-ready-local-rc.md),
and the deployment inputs are derived into
[`docs/architecture/phase3-deployment-contract.md`](docs/architecture/phase3-deployment-contract.md).
Day 15 remains historical readiness evidence; AU-2 remains evaluation-only in
[`docs/architecture/au-2-risk-evaluation.md`](docs/architecture/au-2-risk-evaluation.md).

## Credential-free Local-First flow

Phase 1 inspects deterministic AWS-shaped resources and creates an inert, evidence-bound proposal.
Phase 2 adds authenticated approve/deny/resume behavior, nonce and replay protection, write-before-
execute idempotency, a separately persisted mock inventory, and independent read-back verification.
Both phases reuse the canonical Non-Zero run, checkpoint, and transition contracts. They discover no
AWS credentials and make no cloud network calls.

Run the complete Phase 3 jury story—including approve, deny, replay rejection, pending-approval
restart recovery, terminal reconciliation, and fail-closed probes—in one command:

```bash
.venv/bin/python scripts/phase3/run_jury_demo.py
```

Run a standalone approved or denied terminal demonstration:

```bash
.venv/bin/python scripts/run_local_hitl_demo.py \
  --scenario elastic-ip \
  --decision approved
.venv/bin/python scripts/run_local_hitl_demo.py \
  --scenario security-group \
  --decision denied
```

Run the same workflow through the loopback-only API and embedded operator console:

```bash
.venv/bin/python scripts/run_local_hitl_api.py
```

Open `http://127.0.0.1:8765`, then paste the contents of the owner-only
`.local/aioa-local-api.token` file into the session field. The page keeps the token only in memory;
the API binds only to `127.0.0.1`, requires an exact Bearer header, rejects ambiguous JSON and query
authority, and returns `Cache-Control: no-store` plus a strict content-security policy.

The original Phase 1-only entry point remains available:

```bash
.venv/bin/python scripts/run_local_phase1_demo.py \
  --state-path .local/aioa-local-phase1-state.json
.venv/bin/python -m pytest -q \
  tests/unit/test_local_first_contracts.py \
  tests/unit/test_local_first_tools_and_providers.py \
  tests/unit/test_local_file_state_store.py \
  tests/integration/test_local_first_phase_one.py \
  tests/integration/test_local_hitl_execution.py \
  tests/unit/test_local_hitl_api.py \
  tests/integration/test_local_hitl_http_server.py
```

`AIOA_LOCAL_MODE=mock` is the safe default. An explicit `live` request fails closed; it never falls
back silently to mock mode. See
[`docs/architecture/local-first-phase-1.md`](docs/architecture/local-first-phase-1.md) for the read/
plan foundation and [`docs/architecture/local-first-phase-2.md`](docs/architecture/local-first-phase-2.md)
for authorization, execution, API, recovery, and verification invariants. The
[`demo runbook`](docs/submission/demo-runbook.md) and
[`Devpost draft`](docs/submission/devpost-draft.md) are local preparation artifacts, not proof of an
external submission or live AWS execution.

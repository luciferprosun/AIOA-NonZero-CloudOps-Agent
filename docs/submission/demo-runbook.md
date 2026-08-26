# Local Demo Runbook

Status: prepared for owner review; local mock only; no AWS credentials or cloud writes.

## Fast proof

From the repository root after the documented install:

```bash
.venv/bin/python scripts/run_local_hitl_demo.py --scenario elastic-ip --decision approved
.venv/bin/python scripts/run_local_hitl_demo.py --scenario security-group --decision denied
```

The approved run must report `SUCCESS_WITH_EVIDENCE`, `mock_mutation_count: 1`, and
`network_calls: 0`, with non-null evidence, proposal, receipt, and verification hashes. The denied
run must report `DENIED_BY_HUMAN`, `mock_mutation_count: 0`, `network_calls: 0`, and null receipt and
verification hashes.

## Three-minute operator-console narrative

1. Start the loopback server with `.venv/bin/python scripts/run_local_hitl_api.py`.
2. Open `http://127.0.0.1:8765`. Explain that the server refuses public binding and that the token
   comes from an owner-only local file, not from AWS or browser storage.
3. Paste `.local/aioa-local-api.token` into the token field and connect.
4. Choose **Unattached Elastic IP** and start the bounded run. Point out the typed evidence,
   `PLAN_AND_CONFIRM`, exact target/parameters, proposal/evidence hashes, expiry, and
   `authorizes_execution: false`.
5. Request the exact proposal challenge. Explain that only the nonce hash is durable.
6. Approve. Show that the durable state is `APPROVED`, not success and not yet executed.
7. Resume protected execution. Show the receipt, the independent verification hash, and
   `SUCCESS_WITH_EVIDENCE`.
8. Press resume again. Show `reconciled: true`; the persisted executor count remains one in the
   deterministic automated proof.
9. Start a **Public SSH ingress** run, request its challenge, deny it, and resume. Show
   `DENIED_BY_HUMAN` with no receipt or verification.

## Honest narration

Say “AWS-shaped deterministic local inventory” and “protected mock mutation.” Do not call the demo a
live AWS deployment, effective IAM proof, Bedrock invocation, or real EC2 change. The value being
demonstrated is human authority and verifiable execution ordering even when cloud access is absent.

## Verification before recording

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest -q
.venv/bin/python scripts/run_p0_gate.py
.venv/bin/python scripts/run_p1_gate.py
.venv/bin/python scripts/build_reviewer_evidence_manifest.py --check
.venv/bin/python scripts/validate_reviewer_evidence_manifest.py
```

Use a fresh generated run directory for each recording attempt. Do not place tokens, credentials,
account IDs, private host paths, raw prompts, or provider responses in screenshots or submission
artifacts.

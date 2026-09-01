# Judge-Safe Local Sandbox

## Safety boundary

`scripts/run_portable_demo.py` is the one canonical deterministic judge command. It starts in
portable/mock mode, exercises the real Strands Agent, and then reuses the existing Local-2 and Phase
3 Non-Zero verifier contracts. It does not emulate an AWS account. Its bounded inventory contains
only typed, synthetic EC2/EIP/security-group-shaped resources and permits only allow-listed local
state transitions.

The sandbox has no arbitrary shell tool, URL tool, SDK client, credential discovery, cloud mutation,
or implicit network path. A proposal is always inert. Human approval remains an exact hash-bound
decision and cannot authorize a different target, operation, parameters, evidence version, actor,
expiry, or nonce.

## Golden scenarios

### A — explicit approval

The verifier detects a synthetic unattached elastic IP, creates evidence and an inert proposal,
persists a pending approval, recovers it after a fresh runtime starts, and accepts an exact human
approval. Only then does the bounded executor release the synthetic resource. An independent read
confirms the expected state before `SUCCESS_WITH_EVIDENCE`. Exactly one sandbox mutation occurs.

### B — human denial

A separate synthetic public-ingress proposal reaches the same human boundary. The decision is
denied, the terminal state is `DENIED_BY_HUMAN`, no execution or verification receipt exists, and
the resource remains unchanged. Mutation count is zero.

### C — failure, replay and recovery

The verifier rejects missing approval, resource-binding mismatch, invalid model access, invalid
identity, and invalid verification evidence before mutation. It rejects a conflicting replay with
zero mutation delta. A new runtime reconciles the committed approved receipt after restart without
executing again. Separate Strands tests prove malformed output and provider failure end in durable
typed failure and cannot call the sandbox mutator.

## Evidence bundle

The JSON document has receipt type `AIOA_PORTABLE_JUDGE_SANDBOX` and a canonical SHA-256 over all
fields except its own digest. It embeds—not duplicates—the existing
`PostDeployVerificationReceipt` schema. The bundle records:

- portable runtime, explicit mock provider, Strands package version, canonical agent ID and tools;
- run, trace, correlation, proposal and evidence identifiers/hashes;
- policy/decision/receipt/verification/durable provenance hashes;
- approve, deny, binding-failure, replay and recovery outcomes;
- before-decision, approved, denied, replay and recovered mutation counts;
- provider/external network, AWS call and AWS mutation counts; and
- one final bundle digest with an owner-only on-disk copy.

Raw bearer tokens, decision nonces, AWS account identifiers, resource IDs, credentials, and secrets
are excluded. The output writer uses an atomic owner-only file and rejects a symlink target.

## Reproduce

```bash
AIOA_RUNTIME_MODE=portable \
AIOA_MODEL_PROVIDER=mock \
AIOA_AWS_INTEGRATION_ENABLED=false \
AWS_EC2_METADATA_DISABLED=true \
.venv/bin/python scripts/run_portable_demo.py
```

Expected top-level proof:

```text
status=PASS
runtime_mode=portable
provider=mock
strands_agent.framework=strands-agents
nonzero_verification.approved_path.final_state=SUCCESS_WITH_EVIDENCE
nonzero_verification.deny_path.final_state=DENIED_BY_HUMAN
nonzero_verification.approved_path.replay_rejected=true
nonzero_verification.approved_path.recovery_reconciled=true
external_network_connections=0
aws_calls=0
aws_mutations=0
```

Run the dedicated suite with AWS credentials absent:

```bash
env -u AWS_ACCESS_KEY_ID \
    -u AWS_SECRET_ACCESS_KEY \
    -u AWS_SESSION_TOKEN \
    -u AWS_PROFILE \
    -u AWS_DEFAULT_PROFILE \
    .venv/bin/python -m pytest -q tests/integration/test_portable_judge_sandbox.py
```

The loopback-only local API remains available for interactive human approval. It uses the same
Local-2 authority and persistence contracts and does not require AWS, but it is not a second
deterministic judge launcher and is not required by the portable evidence command.

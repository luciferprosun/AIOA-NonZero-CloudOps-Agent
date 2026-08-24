# Day 15 deployment blocker report

- Status: `BLOCKED`
- Decision: `DO_NOT_DEPLOY`
- Ready for deployment: `NO`

The bounded Day 15 implementation and deterministic Lambda ZIP were built locally. The full local deployment gate returned 7 `PASS`, 3 `BLOCKED`, and 0 `FAIL`. Because D15-G02, D15-G04, and D15-G10 are not `PASS`, no CloudFormation change set or stack deployment was attempted.

## Candidate evidence

- Region guard and explicit preflight: `eu-central-1`, `PASS`.
- Bounded token-window preflight: `PASS`; the expiry value is intentionally not recorded.
- Lambda configuration SHA-256: `67afd13d45f19b62993a78bd8a1ae61a6b67364370791533615ed53a2ebe830f`.
- Deterministic ZIP SHA-256: `9fa6fb7e7ac2ef043d4a323ec327d3dbc3b04b73f3fd56332bbe561355776f32`.
- Artifact manifest SHA-256: `8da0a19707a3716e354bd82972dae756df759a7f2978ceab0e93972dafa5d4e0`.
- Source chain: start `aa941a989a8b8cd0e40367bb130472e9f3c082a7`, M1 `17d5f4637dbd69a33eff1cbb46282c36b19ce6ad`, M2 `8e4583ac9341cb7b66de47cf0e7b2a442ac67b32`.
- The gate was evaluated in a clean detached worktree at M2. The tracked `day15-local-gate-m2.json` canonical output has SHA-256 `7b33d63945503b4691a8c23c7410ecc7a91c265ee887295e06f3a20716e82ecc`.

## Blocking evidence

- D15-G02: SAM CLI is unavailable, so a rendered IAM template and `sam validate --lint` proof do not exist.
- D15-G04: `pip-audit` is unavailable, so the mandatory vulnerability scan is `BLOCKED`.
- D15-G04: no pinned Lambda-compatible container/engine is available, so the mandatory container import proof is `BLOCKED`.
- D15-G10: no authenticated, candidate-bound operator attestation was provided for the encrypted artifact bucket, judge-secret plan, exact sandbox target, Nova 2 access, or owned cost notifications at USD 10/25/40.

Separately from the local gate result, the safe external-preflight identity read did not return an authorized AWS identity. This is an external observation, not an additional reason emitted by D15-G10.

These statements describe missing evidence, not claims that the external resources do not exist. They must be proven by an authorized operator without committing identifiers, recipients, credentials, or secret material.

## AWS safety outcome

- AWS write calls performed: `NO`.
- Change set created: `NO`.
- Stack, Function URL, private executor, DynamoDB table, or judge secret deployed: `NO`.
- Public/private executor invocation performed: `NO`.
- Live `ec2:StopInstances` called: `NO`.

Deployment can be reconsidered only after the same M2 candidate receives all mandatory local toolchain proofs and a valid HMAC-authenticated external preflight receipt, after which the ten-gate result must be recomputed as all `PASS`.

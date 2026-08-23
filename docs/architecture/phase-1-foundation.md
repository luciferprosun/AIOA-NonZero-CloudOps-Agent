# Phase 1 Foundation

This repository is a new implementation for the AWS Agents for Humans Hackathon. No source code from legacy AIOA, AOIA, Non-Zero, Memory Patch, or jury projects is imported.

## Non-Zero Contracts

Non-Zero means no silent, ambiguous, untraceable, or unverifiable execution state may be accepted as valid. Every execution carries:

- an explicit lifecycle state: `INIT`, `RUNNING`, `PENDING`, `SUCCESS`, or `FAIL`;
- an authority gate: `AUTO`, `PLAN_AND_CONFIRM`, or `NEVER_AUTONOMOUS`;
- positive, bounded turn and token budgets;
- a UUIDv7 correlation identifier and a non-empty idempotency key;
- typed errors with a stable code, message, and retryability decision.

`AUTO` is reserved for read-only operations. `PLAN_AND_CONFIRM` permits proposal generation but requires explicit human approval before execution. `NEVER_AUTONOMOUS` prohibits autonomous mutation.

Lifecycle transitions are deterministic. `SUCCESS` and `FAIL` are terminal, and illegal transitions fail explicitly.

UUIDv7 generation is intentionally deferred: this foundation validates UUIDv7 values but does not fake them with UUIDv4 or add a generation dependency.

AWS deployment, AWS resources, agent orchestration, Strands, Bedrock, and remediation actions are intentionally outside this step.

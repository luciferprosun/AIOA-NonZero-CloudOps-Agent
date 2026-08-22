# Hackathon Decision Register

## D-001 — New Independent Repository

- Date: 2026-08-22
- Status: ACCEPTED
- Decision: Build the hackathon entry in a newly initialized, independent repository.
- Rationale: A clean repository creates a provable competition boundary and protects all prior work.
- Reversal condition: None during this hackathon bootstrap; any future repository-boundary change requires explicit written approval before implementation.

## D-002 — No Legacy Implementation Import

- Date: 2026-08-22
- Status: ACCEPTED
- Decision: NO_LEGACY_CODE_IMPORT = TRUE.
- Rationale: Prior projects may inform concepts, but this hackathon implementation must be newly authored.
- Reversal condition: No reversal is authorized in the current competition boundary. Any future exception must be explicitly approved and publicly disclosed before import.

## D-003 — Professional Agents Track

- Date: 2026-08-22
- Status: ACCEPTED
- Decision: Enter the Professional Agents track.
- Rationale: The project is intended to address professional CloudOps work with explicit authority and evidence controls.
- Reversal condition: Only an official eligibility or submission-rule constraint may trigger a documented track review.

## D-004 — Python

- Date: 2026-08-22
- Status: ACCEPTED
- Decision: Use Python as the implementation language.
- Rationale: Python is the planned language for the agent and deterministic application layer.
- Reversal condition: Only demonstrated platform incompatibility may trigger a documented language review.

## D-005 — Strands Agents SDK Is Structurally Central

- Date: 2026-08-22
- Status: ACCEPTED
- Decision: The Strands Agents SDK must be structurally central to the planned agent architecture.
- Rationale: The orchestration foundation must be substantive rather than decorative.
- Reversal condition: Only documented SDK unavailability or incompatibility may trigger a formal Go/No-Go review.

## D-006 — Single-Agent Architecture

- Date: 2026-08-22
- Status: ACCEPTED
- Decision: Start with a single Strands agent.
- Rationale: A single-agent design minimizes coordination ambiguity while the exact product scope is being frozen.
- Reversal condition: Later evidence must prove that one agent is insufficient before a multi-agent design is approved.

## D-007 — DynamoDB as Planned Durable Source of Truth

- Date: 2026-08-22
- Status: ACCEPTED
- Decision: Plan DynamoDB as the durable source of truth.
- Rationale: Durable state must be explicit and separate from model output.
- Reversal condition: A later product-scope or compatibility review must demonstrate that DynamoDB cannot satisfy the frozen use case.

## D-008 — S3 as Planned Evidence and Artifact Store

- Date: 2026-08-22
- Status: ACCEPTED
- Decision: Plan S3 as the evidence and artifact store.
- Rationale: Evidence artifacts require durable, inspectable storage outside transient agent context.
- Reversal condition: A later product-scope review must demonstrate a concrete incompatibility.

## D-009 — Authority Model

- Date: 2026-08-22
- Status: ACCEPTED
- Decision: AUTHORITY_MODEL = AUTO / PLAN_AND_CONFIRM / NEVER_AUTONOMOUS.
- Rationale: Every operation must have an explicit authority class; no ambiguous authorization state is valid.
- Reversal condition: Changes require explicit governance review and evidence that Non-Zero safety properties remain intact.

## D-010 — AgentCore Outside the P0 Critical Path

- Date: 2026-08-22
- Status: ACCEPTED
- Decision: AGENTCORE = NOT_ON_P0_CRITICAL_PATH.
- Rationale: P0 must not depend on an optional platform decision before the core product contract is proven.
- Reversal condition: A later documented Go/No-Go decision may add AgentCore without making the already-proven P0 path contingent on it.

## D-011 — Exact CloudOps Problem Intentionally Unfrozen

- Date: 2026-08-22
- Status: OPEN
- Decision: EXACT_CLOUDOPS_USE_CASE = NOT_YET_FROZEN.
- Rationale: The exact problem must be selected through a dedicated product-scope phase rather than invented during repository bootstrap.
- Reversal condition: Freeze only through the authorized product-scope decision process.

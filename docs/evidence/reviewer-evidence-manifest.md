# Reviewer Evidence Manifest

This judge-facing view is generated from the canonical JSON. It is reviewer proof, not runtime authority.

- Evidence snapshot: `fbb536400594306f2bb3abd31c7064a66735c82d`
- Manifest SHA-256: `46508abd9784fc802d3cdfdd25b1b79515e8f0e0d6ba854212b5a591bc1692b4`
- Primary agents: `1`
- Canonical tools: `inspect_instance, read_utilization_metrics, build_remediation_evidence, stop_sandbox_instance, verify_instance_state`
- Bedrock model: `eu.amazon.nova-2-lite-v1:0` in `eu-central-1`
- Strands Agents: `1.53.0`
- P0: `15/15 PASS`, `136` proof cases
- P1: `6/6 PASS`, `93` proof cases
- Claims: `19`
- Sanitized live receipts: `0`

| Claim ID | Status | Kind | Scope | Conservative claim |
| --- | --- | --- | --- | --- |
| AGENT-TOPOLOGY-01 | PROVEN | TEST | Local deterministic | The runtime factory creates one primary Strands Agent. |
| APPROVAL-BINDING-01 | PROVEN | TEST | mocked AWS | Human approval is explicit and bound to the proposal, request, actor session, and decision nonce. |
| BOUNDED-FAILURES-01 | PROVEN | TEST | Local deterministic | Schema correction, dependency retry, circuit suppression, and workflow budgets are finite and typed. |
| DEFAULT-DENY-01 | PROVEN | TEST | Local deterministic | Unknown and NEVER_AUTONOMOUS capabilities are denied by deterministic policy. |
| EXECUTOR-GATES-01 | PROVEN | TEST | mocked AWS | The private stop executor requires durable prerequisites, exact sandbox scope, both live opt-ins, and an emergency-veto release immediately before write boundaries. |
| IAM-SEPARATION-01 | PROVEN | STATIC | Local deterministic | The checked-in orchestrator policy can invoke only the private executor and has no direct EC2 StopInstances action. |
| IDEMPOTENCY-01 | PROVEN | TEST | mocked AWS | A duplicate logical action cannot silently execute twice while durable idempotency state is acknowledged or unresolved. |
| LIVE-EC2-01 | NOT_YET_PROVEN | DOC | live AWS | A live EC2 StopInstances event is not yet proven by this repository. |
| MODEL-AUTHORITY-01 | PROVEN | TEST | Local deterministic | Model output cannot itself authorize mutation; execution requires deterministic policy and durable human authority. |
| MODEL-PIN-01 | PROVEN | STATIC | Local deterministic | The default Bedrock model configuration selects Amazon Nova 2 Lite in eu-central-1. |
| P0-GATE-01 | PROVEN | TEST | Local deterministic | The canonical P0 matrix passed all 15 gates with 136 proof cases at the evidence snapshot commit. |
| P1-GATE-01 | PROVEN | TEST | Local deterministic | The canonical P1 matrix passed all 6 gates with 93 proof cases at the evidence snapshot commit. |
| PRIOR-ART-ATTESTATION-01 | ATTESTED_ONLY | OPERATOR_ATTESTATION | documentation | The project disclosure states that no prior-project implementation assets were imported. |
| PRIOR-ART-HISTORY-01 | PROVEN | GIT | Local deterministic | The frozen Phase 1 tag, pre-armor ancestry, and prior-art document blobs remain at their recorded immutable anchors. |
| PROPOSAL-DURABILITY-01 | PROVEN | TEST | mocked AWS | An ActionProposal is persisted before approval and never authorizes execution by itself. |
| RECOVERY-NO-REPLAY-01 | PROVEN | TEST | mocked AWS | Restart and lost acknowledgement paths reconcile durable evidence and do not blindly replay mutation. |
| SDK-PIN-01 | PROVEN | STATIC | Local deterministic | The project dependency declares an exact Strands Agents SDK pin at 1.53.0. |
| TOOL-SURFACE-01 | PROVEN | TEST | Local deterministic | The primary agent exposes exactly the five canonical principal tools derived from the runtime factory. |
| VERIFIED-SUCCESS-01 | PROVEN | TEST | mocked AWS | SUCCESS_WITH_EVIDENCE is reached only after independent verification evidence is durably recorded. |

## Exact proof map

### AGENT-TOPOLOGY-01

The runtime factory creates one primary Strands Agent.

- Status / kind / scope: `PROVEN` / `TEST` / `Local deterministic`
- Commit anchor: `fbb536400594306f2bb3abd31c7064a66735c82d`
- Authority source:
  - `src/aioa_cloudops_agent/agent/factory.py::PRIMARY_AGENT_COUNT`
- Proof nodes:
  - `P0-01`
  - `tests/unit/test_strands_agent.py::test_factory_creates_exactly_one_primary_agent_and_five_canonical_tools`
- Limitations: Proves the repository runtime factory, not the topology of an undeployed AWS stack.
- Claim SHA-256: `5549d3da58fc9e52e854d5e67beb03e2ee5da549b30ca09e55b2ed1a58ee0be9`

### APPROVAL-BINDING-01

Human approval is explicit and bound to the proposal, request, actor session, and decision nonce.

- Status / kind / scope: `PROVEN` / `TEST` / `mocked AWS`
- Commit anchor: `fbb536400594306f2bb3abd31c7064a66735c82d`
- Authority source:
  - `src/aioa_cloudops_agent/agent/approval_flow.py::DurableApprovalFlow.resume`
  - `src/aioa_cloudops_agent/nz/contracts.py::Approval.validate_action_binding`
  - `src/aioa_cloudops_agent/persistence/durable_logic.py::validate_approval_binding`
- Proof nodes:
  - `P0-05`
  - `tests/integration/test_durable_hitl_approval_flow.py::test_changed_decision_nonce_replay_is_rejected_without_second_tool_call`
  - `tests/unit/test_durable_memory_repository.py::test_approval_from_another_run_or_proposal_cannot_authorize_execution`
- Limitations: Does not attest to a real operator approval or a deployed identity provider.
- Claim SHA-256: `c9bc831250f30892632149d53e078bb35a5567a888d59ccebf6474b4a4890193`

### BOUNDED-FAILURES-01

Schema correction, dependency retry, circuit suppression, and workflow budgets are finite and typed.

- Status / kind / scope: `PROVEN` / `TEST` / `Local deterministic`
- Commit anchor: `fbb536400594306f2bb3abd31c7064a66735c82d`
- Authority source:
  - `src/aioa_cloudops_agent/safety/circuit.py::DependencyCircuitBreaker.acquire`
  - `src/aioa_cloudops_agent/safety/retry.py::BoundedReadRetry.run`
  - `src/aioa_cloudops_agent/safety/schema.py::SchemaCorrectionBudget`
- Proof nodes:
  - `P0-12`
  - `P0-13`
  - `P1-03`
  - `tests/unit/test_dependency_circuit_breaker.py::test_open_circuit_suppresses_provider_calls_during_cooldown`
- Limitations: Process-local circuit state does not suppress failures across separate cold runtimes.
- Claim SHA-256: `de5122b33ad9d9fdd5be63d7577f575a3b28d948b91c31526ba2a369ced42925`

### DEFAULT-DENY-01

Unknown and NEVER_AUTONOMOUS capabilities are denied by deterministic policy.

- Status / kind / scope: `PROVEN` / `TEST` / `Local deterministic`
- Commit anchor: `fbb536400594306f2bb3abd31c7064a66735c82d`
- Authority source:
  - `src/aioa_cloudops_agent/nz/authority.py::authority_for_capability`
  - `src/aioa_cloudops_agent/safety/policy.py::DefaultDenyToolPolicy.evaluate`
- Proof nodes:
  - `P0-11`
  - `P1-01`
  - `tests/unit/test_safety_hardening.py::test_unknown_tool_alias_defaults_to_policy_denial`
- Limitations: Proves the registered policy boundary, not protection from every future code change.
- Claim SHA-256: `24321e971a48e35e24604d412cbddf5468720a2fe5ebfe89e3d169badc429530`

### EXECUTOR-GATES-01

The private stop executor requires durable prerequisites, exact sandbox scope, both live opt-ins, and an emergency-veto release immediately before write boundaries.

- Status / kind / scope: `PROVEN` / `TEST` / `mocked AWS`
- Commit anchor: `fbb536400594306f2bb3abd31c7064a66735c82d`
- Authority source:
  - `src/aioa_cloudops_agent/persistence/prerequisites.py::load_execution_prerequisites`
  - `src/aioa_cloudops_agent/remediation/emergency.py::EnvironmentEmergencyExecutionControl.assert_writes_enabled`
  - `src/aioa_cloudops_agent/remediation/executor.py::Ec2SandboxStopExecutor.execute`
- Proof nodes:
  - `P0-06`
  - `tests/unit/test_private_sandbox_remediation.py::test_emergency_flip_after_dryrun_blocks_live_stop_call`
  - `tests/unit/test_private_sandbox_remediation.py::test_private_executor_requires_both_live_flags_before_any_aws_call`
- Limitations: Proves fail-closed code paths with fakes; it does not prove a deployed role or a live stop.
- Claim SHA-256: `6293f8a189fcbbc9066914a79b1579b1f31264d4fe8fc7d96af7d6d2c1af8eb3`

### IAM-SEPARATION-01

The checked-in orchestrator policy can invoke only the private executor and has no direct EC2 StopInstances action.

- Status / kind / scope: `PROVEN` / `STATIC` / `Local deterministic`
- Commit anchor: `fbb536400594306f2bb3abd31c7064a66735c82d`
- Authority source:
  - `infra/iam/cloudops-orchestrator-policy.json#lambda:InvokeFunction`
- Proof nodes:
  - `P0-07`
  - `P1-04`
  - `tests/unit/test_iam_policies.py::test_orchestrator_can_invoke_only_private_executor_and_cannot_stop_ec2`
- Limitations: Validates repository policy documents, not the effective policy of an undeployed AWS role.
- Claim SHA-256: `66f42e9ec4ce5e9f3d7ab3a5d7ce1217b0e9fee0270ea300fd242189b74afb56`

### IDEMPOTENCY-01

A duplicate logical action cannot silently execute twice while durable idempotency state is acknowledged or unresolved.

- Status / kind / scope: `PROVEN` / `TEST` / `mocked AWS`
- Commit anchor: `fbb536400594306f2bb3abd31c7064a66735c82d`
- Authority source:
  - `src/aioa_cloudops_agent/persistence/prerequisites.py::register_approved_action`
  - `src/aioa_cloudops_agent/persistence/semantic_idempotency.py::derive_action_fingerprint`
- Proof nodes:
  - `P0-08`
  - `tests/unit/test_private_sandbox_remediation.py::test_duplicate_acknowledged_action_never_invokes_executor_twice`
- Limitations: Does not prove production DynamoDB availability or a live concurrency event.
- Claim SHA-256: `136953d7b50b75f8bba353102e9bb9b1978c8d7292a8206293234b7248de7dfc`

### LIVE-EC2-01

A live EC2 StopInstances event is not yet proven by this repository.

- Status / kind / scope: `NOT_YET_PROVEN` / `DOC` / `live AWS`
- Commit anchor: `fbb536400594306f2bb3abd31c7064a66735c82d`
- Authority source:
  - `docs/architecture/day-14-p1-resilience.md#Deployment remains deferred to Day 15.`
- Proof nodes:
  - None: no live receipt is present.
- Limitations: No sanitized live receipt is present; source and mocked tests prove only bounded capability behavior.
- Claim SHA-256: `c3631b0219d2cd5910bfdc9ae765aa41604a6c529ebf2af4c1de3da24b3f0765`

### MODEL-AUTHORITY-01

Model output cannot itself authorize mutation; execution requires deterministic policy and durable human authority.

- Status / kind / scope: `PROVEN` / `TEST` / `Local deterministic`
- Commit anchor: `fbb536400594306f2bb3abd31c7064a66735c82d`
- Authority source:
  - `src/aioa_cloudops_agent/agent/hitl.py::DurableProposalHumanInTheLoop`
  - `src/aioa_cloudops_agent/nz/contracts.py::ActionProposal.authorizes_execution`
  - `src/aioa_cloudops_agent/safety/policy.py::DefaultDenyToolPolicy.evaluate`
- Proof nodes:
  - `P0-02`
  - `tests/unit/test_private_sandbox_remediation.py::test_model_like_payload_cannot_construct_privileged_execution_command`
- Limitations: Does not claim the model is intrinsically safe; authority remains outside the model.
- Claim SHA-256: `3c3f70fdabdffba6bc359dc209316fd6a27782d6c9b7fe27bcd06bf7f7c49942`

### MODEL-PIN-01

The default Bedrock model configuration selects Amazon Nova 2 Lite in eu-central-1.

- Status / kind / scope: `PROVEN` / `STATIC` / `Local deterministic`
- Commit anchor: `fbb536400594306f2bb3abd31c7064a66735c82d`
- Authority source:
  - `src/aioa_cloudops_agent/config/agent.py::BedrockSettings`
  - `src/aioa_cloudops_agent/config/agent.py::DEFAULT_BEDROCK_MODEL_ID`
- Proof nodes:
  - `P0-02`
  - `tests/unit/test_strands_agent.py::test_bedrock_provider_uses_explicit_region_model_and_bounds`
- Limitations: Proves configuration and request construction, not a live Bedrock invocation.
- Claim SHA-256: `60d156be0adca553c5b3fdc3d3db83f4d2b49bda91832845d384dca385bec6d1`

### P0-GATE-01

The canonical P0 matrix passed all 15 gates with 136 proof cases at the evidence snapshot commit.

- Status / kind / scope: `PROVEN` / `TEST` / `Local deterministic`
- Commit anchor: `fbb536400594306f2bb3abd31c7064a66735c82d`
- Authority source:
  - `scripts/run_p0_gate.py::GATES`
- Proof nodes:
  - `P0-01`
  - `P0-02`
  - `P0-03`
  - `P0-04`
  - `P0-05`
  - `P0-06`
  - `P0-07`
  - `P0-08`
  - `P0-09`
  - `P0-10`
  - `P0-11`
  - `P0-12`
  - `P0-13`
  - `P0-14`
  - `P0-15`
- Limitations: Records deterministic repository proof; it is not a live AWS deployment test.
- Claim SHA-256: `b2b96383dc125adb9704c7cb4e52eea85e6c4ad2011e231bb43a999e4849c6d0`

### P1-GATE-01

The canonical P1 matrix passed all 6 gates with 93 proof cases at the evidence snapshot commit.

- Status / kind / scope: `PROVEN` / `TEST` / `Local deterministic`
- Commit anchor: `fbb536400594306f2bb3abd31c7064a66735c82d`
- Authority source:
  - `scripts/run_p1_gate.py::GATES`
- Proof nodes:
  - `P1-01`
  - `P1-02`
  - `P1-03`
  - `P1-04`
  - `P1-05`
  - `P1-06`
- Limitations: Records deterministic failure-engineering proof; clean-clone remote mode depends on public-origin reachability.
- Claim SHA-256: `4b7c9f2df8a02dc7e835c9a5e06b28d05e7d6f5fcc07eebfc5d66a492fcfb94d`

### PRIOR-ART-ATTESTATION-01

The project disclosure states that no prior-project implementation assets were imported.

- Status / kind / scope: `ATTESTED_ONLY` / `OPERATOR_ATTESTATION` / `documentation`
- Commit anchor: `fbb536400594306f2bb3abd31c7064a66735c82d`
- Authority source:
  - `PRIOR-ART.md#No implementation code, commits, migrations, deployment definitions, or generated assets from prior projects were imported into this repository.`
- Proof nodes:
  - `P0-15`
- Limitations: Repository scans and disclosure support this statement but cannot prove facts outside the inspected repositories.
- Claim SHA-256: `86778b7df95412a938396de03495dbf7afed44598787e11c6fd0eab935748150`

### PRIOR-ART-HISTORY-01

The frozen Phase 1 tag, pre-armor ancestry, and prior-art document blobs remain at their recorded immutable anchors.

- Status / kind / scope: `PROVEN` / `GIT` / `Local deterministic`
- Commit anchor: `fbb536400594306f2bb3abd31c7064a66735c82d`
- Authority source:
  - `docs/audit/prior-art-june1-forensic-baseline.md`
  - `scripts/run_p0_gate.py::PRIOR_ART_BLOBS`
- Proof nodes:
  - `P0-15`
  - `tests/unit/test_strands_agent.py::test_phase_1_tag_remains_at_frozen_commit`
- Limitations: Proves this repository's anchors and frozen forensic documents; external history claims retain their documented evidence limits.
- Claim SHA-256: `28c0b0c406c0d2e05c82520a46d95d8b061b7de985839bceaf02148fc98009b2`

### PROPOSAL-DURABILITY-01

An ActionProposal is persisted before approval and never authorizes execution by itself.

- Status / kind / scope: `PROVEN` / `TEST` / `mocked AWS`
- Commit anchor: `fbb536400594306f2bb3abd31c7064a66735c82d`
- Authority source:
  - `src/aioa_cloudops_agent/nz/contracts.py::ActionProposal.authorizes_execution`
  - `src/aioa_cloudops_agent/persistence/nz_dynamodb.py::DynamoDbDurableTruthRepository.create_proposal`
- Proof nodes:
  - `P0-04`
  - `tests/integration/test_read_only_investigation_flow.py::test_strands_happy_path_persists_evidence_backed_non_authorizing_proposal`
- Limitations: Proves persistence contracts and mocked repository behavior, not a live DynamoDB write.
- Claim SHA-256: `65870290833508b04ff82076430e1cd0b870fa6f595cbb44777ecb45810e6abc`

### RECOVERY-NO-REPLAY-01

Restart and lost acknowledgement paths reconcile durable evidence and do not blindly replay mutation.

- Status / kind / scope: `PROVEN` / `TEST` / `mocked AWS`
- Commit anchor: `fbb536400594306f2bb3abd31c7064a66735c82d`
- Authority source:
  - `src/aioa_cloudops_agent/recovery/coordinator.py::RecoveryCoordinator.recover`
- Proof nodes:
  - `P0-10`
  - `tests/unit/test_recovery_reconciliation.py::test_lost_executor_ack_observed_running_requires_operator_and_never_replays`
- Limitations: Proves deterministic recovery behavior with fakes, not a live process interruption.
- Claim SHA-256: `71149b48011d4639579f91872c522232e5dcc81e59a7ca44f0076eea08cdc9c8`

### SDK-PIN-01

The project dependency declares an exact Strands Agents SDK pin at 1.53.0.

- Status / kind / scope: `PROVEN` / `STATIC` / `Local deterministic`
- Commit anchor: `fbb536400594306f2bb3abd31c7064a66735c82d`
- Authority source:
  - `pyproject.toml#strands-agents[otel]==1.53.0`
- Proof nodes:
  - `P0-01`
  - `P1-06`
- Limitations: Proves the declared pin and clean install contract, not future package-index availability.
- Claim SHA-256: `2474fe6eb000c0f17b4beb230dbec9d4fcfc3c88a8790096b8101c1dac7ef830`

### TOOL-SURFACE-01

The primary agent exposes exactly the five canonical principal tools derived from the runtime factory.

- Status / kind / scope: `PROVEN` / `TEST` / `Local deterministic`
- Commit anchor: `fbb536400594306f2bb3abd31c7064a66735c82d`
- Authority source:
  - `src/aioa_cloudops_agent/agent/factory.py::CURRENT_TOOL_NAMES`
  - `src/aioa_cloudops_agent/agent/factory.py::FINAL_TOOL_CAP`
- Proof nodes:
  - `P0-01`
  - `tests/unit/test_strands_agent.py::test_factory_creates_exactly_one_primary_agent_and_five_canonical_tools`
- Limitations: Counts principal Strands tools in this repository, not infrastructure endpoints.
- Claim SHA-256: `6feb89901a397b5c247341a9c29ad89967f29940891bf94e2f6facf54c08a3ae`

### VERIFIED-SUCCESS-01

SUCCESS_WITH_EVIDENCE is reached only after independent verification evidence is durably recorded.

- Status / kind / scope: `PROVEN` / `TEST` / `mocked AWS`
- Commit anchor: `fbb536400594306f2bb3abd31c7064a66735c82d`
- Authority source:
  - `src/aioa_cloudops_agent/nz/enums.py::WorkflowState.SUCCESS_WITH_EVIDENCE`
  - `src/aioa_cloudops_agent/verification/coordinator.py::BoundedVerificationCoordinator.verify`
- Proof nodes:
  - `P0-09`
  - `tests/unit/test_verification_closure.py::test_success_transition_without_durable_verification_evidence_is_rejected`
- Limitations: Proves mocked verification and durable ordering, not a live EC2 observation.
- Claim SHA-256: `b9f3edfc9f2c4db6e756c7c4abb68270bd8669e91c140984318739563184eb84`

## Truthfulness boundary

Static source and mocked tests prove bounded code behavior. They do not prove a live AWS action. A live-event claim remains `NOT_YET_PROVEN` until a separate sanitized receipt is deliberately reviewed and added.

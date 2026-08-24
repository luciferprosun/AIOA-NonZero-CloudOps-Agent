# Reviewer Evidence Manifest

This judge-facing view is generated from the canonical JSON. It is reviewer proof, not runtime authority.

- Frozen Phase 1 / Day 14 snapshot: `fbb536400594306f2bb3abd31c7064a66735c82d`
- Day 15 local candidate snapshot: `36fd17df981dfa593d4e63f6a143410317410763` (`LOCAL_IMPLEMENTATION_CANDIDATE`)
- Day 15 additive recovery lineage: `aa941a989a8b8cd0e40367bb130472e9f3c082a7` -> `17d5f4637dbd69a33eff1cbb46282c36b19ce6ad` -> `8e4583ac9341cb7b66de47cf0e7b2a442ac67b32` -> `30c2a30cda0ac6d6e2003166daf6c29bf2c764f0` -> `f2ee79c09ba174ba72cb527b70c095f412151758` -> `36fd17df981dfa593d4e63f6a143410317410763`
- Day 15 gates: `D15-G01, D15-G02, D15-G03, D15-G04, D15-G05, D15-G06, D15-G07, D15-G08, D15-G09, D15-G10`
- Manifest SHA-256: `5480099e8aedf80dbafbaed5d9e2a6dc994f559ce9ab97df53820cdcdc8b373e`
- Primary agents: `1`
- Canonical tools: `inspect_instance, read_utilization_metrics, build_remediation_evidence, stop_sandbox_instance, verify_instance_state`
- Bedrock model: `eu.amazon.nova-2-lite-v1:0` in `eu-central-1`
- Strands Agents: `1.53.0`
- P0: `15/15 PASS`, `136` proof cases
- P1: `6/6 PASS`, `93` proof cases
- Claims: `26`
- Sanitized live receipts: `0`

| Claim ID | Status | Kind | Scope | Conservative claim |
| --- | --- | --- | --- | --- |
| AGENT-TOPOLOGY-01 | PROVEN | TEST | Local deterministic | The runtime factory creates one primary Strands Agent. |
| APPROVAL-BINDING-01 | PROVEN | TEST | mocked AWS | Human approval is explicit and bound to the proposal, request, actor session, and decision nonce. |
| BOUNDED-FAILURES-01 | PROVEN | TEST | Local deterministic | Schema correction, dependency retry, circuit suppression, and workflow budgets are finite and typed. |
| DAY15-AWS-CLIENT-BOUNDS-01 | PROVEN | TEST | Local deterministic | Critical AWS clients own explicit one-attempt transport configuration, and the bounded model wrapper suppresses repeated warm-runtime failures without a hidden retry. |
| DAY15-COLD-RESUME-01 | PROVEN | TEST | mocked AWS | A fresh Agent runtime can restore a durable native interrupt using trusted principal identity and a server-issued one-time challenge, while no approval or resume route is public. |
| DAY15-DEPLOYMENT-GATE-01 | PROVEN | TEST | Local deterministic | The local Day 15 controller defines exactly ten stable gates, never authorizes deployment in validate-only mode, and blocks when artifact or external prerequisites are absent. |
| DAY15-JUDGE-SURFACE-01 | PROVEN | TEST | Local deterministic | The Day 15 application exposes health, readiness, same-origin UI, and token-protected read-only investigation and status routes; approval and mutation routes fail before services. |
| DAY15-RELEASE-SAFETY-01 | PROVEN | TEST | Local deterministic | The Day 15 candidate uses a hash-locked runtime and template-enforced retained state, explicit region, conditioned URL permissions, immutable aliases, bounded concurrency, and reviewed alias rollback. |
| DAY15-RUNTIME-GUARDS-01 | PROVEN | TEST | mocked AWS | Judge inputs cannot set authority or budgets; fresh investigations use exact server budgets, atomic daily quota reservations, and finite read-only status observations. |
| DAY15-TELEMETRY-01 | PROVEN | TEST | Local deterministic | Judge telemetry exports only allowlisted identifiers and bounded classifications while structured logging discards prompts, secrets, and tool arguments. |
| DEFAULT-DENY-01 | PROVEN | TEST | Local deterministic | Unknown and NEVER_AUTONOMOUS capabilities are denied by deterministic policy. |
| EXECUTOR-GATES-01 | PROVEN | TEST | mocked AWS | The private stop executor requires durable prerequisites, exact sandbox scope, both live opt-ins, and an emergency-veto release immediately before write boundaries. |
| IAM-SEPARATION-01 | PROVEN | STATIC | Local deterministic | The checked-in orchestrator policy can invoke only the private executor and has no direct EC2 StopInstances action. |
| IDEMPOTENCY-01 | PROVEN | TEST | mocked AWS | A duplicate logical action cannot silently execute twice while durable idempotency state is acknowledged or unresolved. |
| LIVE-EC2-01 | NOT_YET_PROVEN | DOC | live AWS | A live EC2 StopInstances event is not yet proven by this repository. |
| MODEL-AUTHORITY-01 | PROVEN | TEST | Local deterministic | Model output cannot itself authorize mutation; execution requires deterministic policy and durable human authority. |
| MODEL-PIN-01 | PROVEN | STATIC | Local deterministic | The default Bedrock model configuration selects Amazon Nova 2 Lite in eu-central-1. |
| P0-GATE-01 | PROVEN | TEST | Local deterministic | The canonical P0 matrix passed all 15 gates with 136 proof cases at its reviewed commit anchor. |
| P1-GATE-01 | PROVEN | TEST | Local deterministic | The canonical P1 matrix passed all 6 gates with 93 proof cases at its reviewed commit anchor. |
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
- Commit anchor: `17d5f4637dbd69a33eff1cbb46282c36b19ce6ad`
- Authority source:
  - `src/aioa_cloudops_agent/agent/factory.py::PRIMARY_AGENT_COUNT`
- Proof nodes:
  - `P0-01`
  - `tests/unit/test_strands_agent.py::test_factory_creates_exactly_one_primary_agent_and_five_canonical_tools`
- Limitations: Proves the repository runtime factory, not the topology of an undeployed AWS stack.
- Claim SHA-256: `458e4b96b52819343c8d4dcc31708df1b9ee0d3f1d1d7251185e40accbaed51e`

### APPROVAL-BINDING-01

Human approval is explicit and bound to the proposal, request, actor session, and decision nonce.

- Status / kind / scope: `PROVEN` / `TEST` / `mocked AWS`
- Commit anchor: `f2ee79c09ba174ba72cb527b70c095f412151758`
- Authority source:
  - `src/aioa_cloudops_agent/agent/approval_flow.py::DurableApprovalFlow.resume`
  - `src/aioa_cloudops_agent/nz/contracts.py::Approval.validate_action_binding`
  - `src/aioa_cloudops_agent/persistence/durable_logic.py::validate_approval_binding`
- Proof nodes:
  - `P0-05`
  - `tests/integration/test_durable_hitl_approval_flow.py::test_changed_decision_nonce_replay_is_rejected_without_second_tool_call`
  - `tests/unit/test_durable_memory_repository.py::test_approval_from_another_run_or_proposal_cannot_authorize_execution`
- Limitations: Does not attest to a real operator approval or a deployed identity provider.
- Claim SHA-256: `4c9eadb152ff1842da68d8b618953c3cd1c06b4932914424a230fee0cc5a9b05`

### BOUNDED-FAILURES-01

Schema correction, dependency retry, circuit suppression, and workflow budgets are finite and typed.

- Status / kind / scope: `PROVEN` / `TEST` / `Local deterministic`
- Commit anchor: `17d5f4637dbd69a33eff1cbb46282c36b19ce6ad`
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
- Claim SHA-256: `7f5b4c1858a38742a1f62b557537ed56b17d7c2080e2b2b3775370554d8a1674`

### DAY15-AWS-CLIENT-BOUNDS-01

Critical AWS clients own explicit one-attempt transport configuration, and the bounded model wrapper suppresses repeated warm-runtime failures without a hidden retry.

- Status / kind / scope: `PROVEN` / `TEST` / `Local deterministic`
- Commit anchor: `17d5f4637dbd69a33eff1cbb46282c36b19ce6ad`
- Authority source:
  - `src/aioa_cloudops_agent/aws_clients.py::_bounded_config`
  - `src/aioa_cloudops_agent/safety/model_circuit.py::CircuitBoundedModel`
- Proof nodes:
  - `tests/unit/test_day15_aws_clients.py::test_configured_endpoint_environment_cannot_redirect_real_client`
  - `tests/unit/test_day15_aws_clients.py::test_critical_client_factories_own_region_timeouts_and_retry_count`
  - `tests/unit/test_day15_model_circuit.py::test_model_circuit_suppresses_third_warm_call_without_hidden_retry`
- Limitations: Tests inspect client construction and deterministic fakes; they do not attest to provider latency or availability.
- Claim SHA-256: `a1c436c361ad4a9f2c5395039ce113daaf29e668ad096fb12655cd4dbdba0a52`

### DAY15-COLD-RESUME-01

A fresh Agent runtime can restore a durable native interrupt using trusted principal identity and a server-issued one-time challenge, while no approval or resume route is public.

- Status / kind / scope: `PROVEN` / `TEST` / `mocked AWS`
- Commit anchor: `f2ee79c09ba174ba72cb527b70c095f412151758`
- Authority source:
  - `src/aioa_cloudops_agent/agent/factory.py::create_primary_agent`
  - `src/aioa_cloudops_agent/deployment/resume.py::AuthenticatedApprovalResumeService`
- Proof nodes:
  - `tests/integration/test_durable_hitl_approval_flow.py::test_fresh_process_restores_native_interrupt_with_trusted_one_time_freshness`
  - `tests/unit/test_day15_judge_http.py::test_unknown_approval_mutation_and_wrong_method_routes_fail_before_services`
- Limitations: Proves deterministic restoration and duplicate rejection with local durable fakes; the capability remains absent from the public route table.
- Claim SHA-256: `dd6c0eadf66bb3add46056f8b303e877bbb0b52b58e33d6bec31bf7c705cbb26`

### DAY15-DEPLOYMENT-GATE-01

The local Day 15 controller defines exactly ten stable gates, never authorizes deployment in validate-only mode, and blocks when artifact or external prerequisites are absent.

- Status / kind / scope: `PROVEN` / `TEST` / `Local deterministic`
- Commit anchor: `36fd17df981dfa593d4e63f6a143410317410763`
- Authority source:
  - `scripts/day15/external_preflight_attestation.py::validate_receipt`
  - `scripts/day15/render_template.py::verify_rendered_template`
  - `scripts/day15/run_day15_gate.py::GATES`
  - `scripts/day15/run_day15_gate.py::_payload`
  - `scripts/day15/run_day15_gate.py::run_gate`
- Proof nodes:
  - `D15-G01`
  - `D15-G02`
  - `D15-G03`
  - `D15-G04`
  - `D15-G05`
  - `D15-G06`
  - `D15-G07`
  - `D15-G08`
  - `D15-G09`
  - `D15-G10`
  - `tests/unit/test_day15_deployment_gate.py::test_deployment_decision_requires_all_ten_gates_to_pass`
  - `tests/unit/test_day15_deployment_gate.py::test_g02_requires_authenticated_render_and_exact_closed_role_allowlists`
  - `tests/unit/test_day15_deployment_gate.py::test_g04_reexecutes_clean_import_archive_dependency_and_container_proofs`
  - `tests/unit/test_day15_deployment_gate.py::test_g10_deployment_contract_is_blocked_until_selected_hashes_are_reviewed`
  - `tests/unit/test_day15_deployment_gate.py::test_local_gate_never_performs_aws_api_calls_and_only_probes_cli_version`
  - `tests/unit/test_day15_external_preflight.py::test_external_contract_names_every_required_confirmation_and_identity`
  - `tests/unit/test_day15_gate.py::test_gate_matrix_has_exact_stable_ids_status_vocabulary_and_validate_only_output`
  - `tests/unit/test_day15_gate.py::test_missing_artifact_and_external_prerequisites_are_reported_as_blocked`
- Limitations: Proves local fail-closed decision logic and gate definitions; external prerequisite satisfaction is outside repository-only proof.
- Claim SHA-256: `dfe98712084bc0697d606e32ee7fbc0b38a1172604e434dd5d5f6e9fc0242f5d`

### DAY15-JUDGE-SURFACE-01

The Day 15 application exposes health, readiness, same-origin UI, and token-protected read-only investigation and status routes; approval and mutation routes fail before services.

- Status / kind / scope: `PROVEN` / `TEST` / `Local deterministic`
- Commit anchor: `17d5f4637dbd69a33eff1cbb46282c36b19ce6ad`
- Authority source:
  - `src/aioa_cloudops_agent/deployment/auth.py::JudgeTokenAuthorizer`
  - `src/aioa_cloudops_agent/judge/application.py::JudgeFunctionUrlApplication`
  - `src/aioa_cloudops_agent/judge/lambda_handler.py::lambda_handler`
- Proof nodes:
  - `tests/unit/test_day15_judge_http.py::test_health_and_root_create_no_clients_and_expose_hardened_same_origin_ui`
  - `tests/unit/test_day15_judge_http.py::test_status_requires_auth_and_global_quota_before_one_bounded_status_read`
  - `tests/unit/test_day15_judge_http.py::test_unknown_approval_mutation_and_wrong_method_routes_fail_before_services`
  - `tests/unit/test_day15_judge_http.py::test_wrong_token_denies_before_quota_agent_and_status`
- Limitations: Proves the checked-in router and local service boundaries, not a deployed Function URL or operator identity system.
- Claim SHA-256: `3f7e3c6766575fb99ed2c48b832fd7fe7c7f71bd151c32941da97e1b41a5314c`

### DAY15-RELEASE-SAFETY-01

The Day 15 candidate uses a hash-locked runtime and template-enforced retained state, explicit region, conditioned URL permissions, immutable aliases, bounded concurrency, and reviewed alias rollback.

- Status / kind / scope: `PROVEN` / `TEST` / `Local deterministic`
- Commit anchor: `36fd17df981dfa593d4e63f6a143410317410763`
- Authority source:
  - `infra/sam/template.yaml`
  - `requirements/day15-toolchain.json`
  - `requirements/lambda-runtime.txt`
  - `scripts/day15/alias_rollback.py::build_plan`
  - `scripts/day15/build_lambda_artifact.py::build_artifact`
  - `scripts/day15/build_lambda_artifact.py::revalidate_artifact`
  - `scripts/day15/preflight_region.py::validate_region`
  - `scripts/day15/render_template.py::render_template`
  - `scripts/day15/validate_template.py::validate_template_toolchain`
- Proof nodes:
  - `tests/unit/test_day15_artifact.py::test_container_validation_binds_engine_version_platform_and_manifest_digest`
  - `tests/unit/test_day15_artifact.py::test_dependency_scan_pass_requires_exact_complete_locked_inventory`
  - `tests/unit/test_day15_artifact.py::test_dependency_scan_rejects_installed_scanner_version_drift`
  - `tests/unit/test_day15_artifact.py::test_repository_provenance_binds_clean_head_index_worktree_and_source_tree`
  - `tests/unit/test_day15_artifact.py::test_runtime_lock_is_complete_exact_and_hash_locked`
  - `tests/unit/test_day15_artifact.py::test_runtime_rebuild_uses_two_distinct_clean_installs`
  - `tests/unit/test_day15_deployment_gate.py::test_g07_requires_semantic_alias_only_rollback_and_executable_proofs`
  - `tests/unit/test_day15_deployment_gate.py::test_g08_rejects_every_forbidden_cost_service`
  - `tests/unit/test_day15_gate.py::test_alias_rollback_requires_reviewed_hash_then_reconciles_both_aliases`
  - `tests/unit/test_day15_render_template.py::test_renderer_is_byte_deterministic_and_verifies_source_tools_and_commit`
  - `tests/unit/test_day15_render_template.py::test_template_validator_requires_exact_sam_lint_and_translator_versions`
  - `tests/unit/test_infrastructure_contract.py::test_function_url_targets_live_alias_and_has_exact_two_conditioned_permissions`
  - `tests/unit/test_infrastructure_contract.py::test_immutable_versions_and_live_aliases_are_retained_for_rollback`
  - `tests/unit/test_infrastructure_contract.py::test_region_is_explicit_and_public_ingress_preserves_all_mutation_vetoes`
  - `tests/unit/test_infrastructure_contract.py::test_state_table_is_retained_recoverable_encrypted_and_deletion_protected`
- Limitations: Proves repository artifact, template, and rollback contracts; it does not prove a built release was installed in an account.
- Claim SHA-256: `78fa975fd49f487132ec8a07a403a8a576db694fb0d5d9cb93ee923df41381b8`

### DAY15-RUNTIME-GUARDS-01

Judge inputs cannot set authority or budgets; fresh investigations use exact server budgets, atomic daily quota reservations, and finite read-only status observations.

- Status / kind / scope: `PROVEN` / `TEST` / `mocked AWS`
- Commit anchor: `f2ee79c09ba174ba72cb527b70c095f412151758`
- Authority source:
  - `src/aioa_cloudops_agent/deployment/config.py::JudgeInvestigationRequest`
  - `src/aioa_cloudops_agent/deployment/config.py::new_judge_budget`
  - `src/aioa_cloudops_agent/deployment/quota.py::DynamoDbJudgeQuotaRepository`
  - `src/aioa_cloudops_agent/deployment/status.py::ReadOnlyRunStatusService`
  - `src/aioa_cloudops_agent/judge/runtime.py::JudgeInvestigationRuntime`
- Proof nodes:
  - `tests/unit/test_day15_judge_runtime.py::test_each_investigation_builds_fresh_snapshot_session_agent_and_server_budget`
  - `tests/unit/test_day15_runtime_contracts.py::test_dynamodb_quota_uses_one_conditional_update_for_all_caps`
  - `tests/unit/test_day15_runtime_contracts.py::test_judge_schema_rejects_caller_authority_and_budget_fields`
  - `tests/unit/test_day15_runtime_contracts.py::test_server_owned_judge_budget_is_exact_and_fresh`
  - `tests/unit/test_day15_runtime_contracts.py::test_status_observation_cap_is_server_enforced_for_every_nonterminal_state`
- Limitations: Proves server-owned bounds with deterministic repositories and clients, not production quota-service availability.
- Claim SHA-256: `47fe98e7fc38e2eb71b50821e28a927fea4472b24899e75913f89e4315a7c653`

### DAY15-TELEMETRY-01

Judge telemetry exports only allowlisted identifiers and bounded classifications while structured logging discards prompts, secrets, and tool arguments.

- Status / kind / scope: `PROVEN` / `TEST` / `Local deterministic`
- Commit anchor: `f2ee79c09ba174ba72cb527b70c095f412151758`
- Authority source:
  - `src/aioa_cloudops_agent/judge/logging.py::StructuredJudgeLogger`
  - `src/aioa_cloudops_agent/judge/telemetry.py::SanitizedXRaySpanExporter`
  - `src/aioa_cloudops_agent/judge/telemetry.py::initialize_judge_telemetry`
- Proof nodes:
  - `tests/unit/test_day15_judge_http.py::test_structured_logger_discards_secrets_prompts_and_tool_arguments`
  - `tests/unit/test_day15_judge_runtime.py::test_runtime_emits_real_allowlisted_operation_span_without_sensitive_values`
  - `tests/unit/test_day15_judge_telemetry.py::test_process_telemetry_uses_exact_sampled_provider_and_empty_unredacted_opt_in`
  - `tests/unit/test_day15_judge_telemetry.py::test_xray_exporter_emits_only_allowlisted_ids_route_outcome_and_dependency`
- Limitations: Proves filtering and exporter construction with local fakes; no provider trace delivery is attested.
- Claim SHA-256: `e7ec3721508a1d3ecfaeb14ef54d31a88678f5a0c4792851dda195c46347f39e`

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
- Commit anchor: `17d5f4637dbd69a33eff1cbb46282c36b19ce6ad`
- Authority source:
  - `src/aioa_cloudops_agent/persistence/prerequisites.py::load_execution_prerequisites`
  - `src/aioa_cloudops_agent/remediation/emergency.py::EnvironmentEmergencyExecutionControl.assert_writes_enabled`
  - `src/aioa_cloudops_agent/remediation/executor.py::Ec2SandboxStopExecutor.execute`
- Proof nodes:
  - `P0-06`
  - `tests/unit/test_private_sandbox_remediation.py::test_emergency_flip_after_dryrun_blocks_live_stop_call`
  - `tests/unit/test_private_sandbox_remediation.py::test_private_executor_requires_both_live_flags_before_any_aws_call`
- Limitations: Proves fail-closed code paths with fakes; it does not prove a deployed role or a live stop.
- Claim SHA-256: `3a37259f4d84b965b196307739b1dc37c1cc25fd6181fa6b53a07fa1f161bb36`

### IAM-SEPARATION-01

The checked-in orchestrator policy can invoke only the private executor and has no direct EC2 StopInstances action.

- Status / kind / scope: `PROVEN` / `STATIC` / `Local deterministic`
- Commit anchor: `17d5f4637dbd69a33eff1cbb46282c36b19ce6ad`
- Authority source:
  - `infra/iam/cloudops-orchestrator-policy.json#lambda:InvokeFunction`
- Proof nodes:
  - `P0-07`
  - `P1-04`
  - `tests/unit/test_iam_policies.py::test_orchestrator_policy_is_exact_read_model_state_secret_and_alias_authority`
- Limitations: Validates repository policy documents, not the effective policy of an undeployed AWS role.
- Claim SHA-256: `a4e2d92454d7ca60e9ef113e76e8e9ce1835ba998511ceca01dcc4b3de443c6e`

### IDEMPOTENCY-01

A duplicate logical action cannot silently execute twice while durable idempotency state is acknowledged or unresolved.

- Status / kind / scope: `PROVEN` / `TEST` / `mocked AWS`
- Commit anchor: `17d5f4637dbd69a33eff1cbb46282c36b19ce6ad`
- Authority source:
  - `src/aioa_cloudops_agent/persistence/prerequisites.py::register_approved_action`
  - `src/aioa_cloudops_agent/persistence/semantic_idempotency.py::derive_action_fingerprint`
- Proof nodes:
  - `P0-08`
  - `tests/unit/test_private_sandbox_remediation.py::test_duplicate_acknowledged_action_never_invokes_executor_twice`
- Limitations: Does not prove production DynamoDB availability or a live concurrency event.
- Claim SHA-256: `59887983b21cea348e7292e4f5ea33b3650f746a3af8c33ebbe21ad6e50f3434`

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
- Commit anchor: `17d5f4637dbd69a33eff1cbb46282c36b19ce6ad`
- Authority source:
  - `src/aioa_cloudops_agent/agent/hitl.py::DurableProposalHumanInTheLoop`
  - `src/aioa_cloudops_agent/nz/contracts.py::ActionProposal.authorizes_execution`
  - `src/aioa_cloudops_agent/safety/policy.py::DefaultDenyToolPolicy.evaluate`
- Proof nodes:
  - `P0-02`
  - `tests/unit/test_private_sandbox_remediation.py::test_model_like_payload_cannot_construct_privileged_execution_command`
- Limitations: Does not claim the model is intrinsically safe; authority remains outside the model.
- Claim SHA-256: `c87f3cfb02cc8f9f19e9b72ae3c6519b28cbc818dbbc58b1a675507fa96226a4`

### MODEL-PIN-01

The default Bedrock model configuration selects Amazon Nova 2 Lite in eu-central-1.

- Status / kind / scope: `PROVEN` / `STATIC` / `Local deterministic`
- Commit anchor: `17d5f4637dbd69a33eff1cbb46282c36b19ce6ad`
- Authority source:
  - `src/aioa_cloudops_agent/config/agent.py::BedrockSettings`
  - `src/aioa_cloudops_agent/config/agent.py::DEFAULT_BEDROCK_MODEL_ID`
- Proof nodes:
  - `P0-02`
  - `tests/unit/test_strands_agent.py::test_bedrock_provider_uses_explicit_region_model_and_bounds`
- Limitations: Proves configuration and request construction, not a live Bedrock invocation.
- Claim SHA-256: `db346dc1ad4b8b8afc224e3a42b8fce97a475d53f3e5bb5fa808a4d888181253`

### P0-GATE-01

The canonical P0 matrix passed all 15 gates with 136 proof cases at its reviewed commit anchor.

- Status / kind / scope: `PROVEN` / `TEST` / `Local deterministic`
- Commit anchor: `17d5f4637dbd69a33eff1cbb46282c36b19ce6ad`
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
- Claim SHA-256: `96b748e9912326b51d55e5292d524ca2b1177aa57447be95126cf2ba88fb425c`

### P1-GATE-01

The canonical P1 matrix passed all 6 gates with 93 proof cases at its reviewed commit anchor.

- Status / kind / scope: `PROVEN` / `TEST` / `Local deterministic`
- Commit anchor: `17d5f4637dbd69a33eff1cbb46282c36b19ce6ad`
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
- Claim SHA-256: `f2fdb898fea44eb2a9f718ba00c02c7716deb163a6e4673e265cc62019649e5d`

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
- Proof nodes:
  - `P0-15`
- Limitations: Proves this repository's anchors and frozen forensic documents; external history claims retain their documented evidence limits.
- Claim SHA-256: `50e6bad1bafba5b25732d2c2661f0c6a3057bbd951ac8e13da9523d2a05040e1`

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
- Commit anchor: `17d5f4637dbd69a33eff1cbb46282c36b19ce6ad`
- Authority source:
  - `src/aioa_cloudops_agent/agent/factory.py::CURRENT_TOOL_NAMES`
  - `src/aioa_cloudops_agent/agent/factory.py::FINAL_TOOL_CAP`
- Proof nodes:
  - `P0-01`
  - `tests/unit/test_strands_agent.py::test_factory_creates_exactly_one_primary_agent_and_five_canonical_tools`
- Limitations: Counts principal Strands tools in this repository, not infrastructure endpoints.
- Claim SHA-256: `3fafc06134c63321841d48097bdfe255048f97ad31a1c0ad339f742aa12ad912`

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

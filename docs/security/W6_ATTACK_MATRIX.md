# W6 hostile-path attack matrix

This matrix records the deterministic attacks applied to the complete W1-W5 workspace hero.
`PASS` means the checked-in proof fails closed, preserves durable truth and creates no
unauthorized semantic effect. It does not mean the product is a public multi-user service.

## Authority and approval

| Attack | Expected invariant | Proof | Result |
| --- | --- | --- | --- |
| Model/client supplies path, content, command, URL, environment, profile, verifier result or approval state | Unknown authority fields are rejected before durable state changes | `test_decision_contract_rejects_every_authority_smuggling_field` and W2/W3 strict contracts | PASS |
| Proposal, patch, evidence, workspace, run, request or verifier identity is substituted | Exact durable identities win; the supplied identity cannot authorize another effect | W2 identity matrix, W3 cross-identity matrix, W5 stale/cross-run tests | PASS |
| A second authenticated operator consumes an existing request after restart/token rotation | Each hero run remains bound to its originating authenticated session | `test_different_authenticated_operator_cannot_consume_an_existing_request` | PASS |
| Approval is replayed after verified success | No second patch or verifier process is created | W5 approve/replay journey and W4 duplicate-verification proof | PASS |
| Denial is reused as approval or resume authority | Denial is terminal and mutation count remains zero | `test_denial_is_terminal_and_cannot_be_reused_as_approval` | PASS |
| Two same-session tabs race resume | At most one semantic effect exists | `test_two_same_session_tabs_can_create_only_one_semantic_effect` | PASS |
| Concurrent approve/deny decisions race | One durable winner; the conflict cannot create an effect | `test_concurrent_conflicting_human_decisions_have_one_durable_winner` | PASS |
| Workspace bytes drift after approval | Pre-effect revalidation rejects the stale approval with zero effect | `test_workspace_drift_after_approval_blocks_the_exact_effect` | PASS |
| A byte-different but semantically similar patch is substituted | Content-addressed proposal identity changes and is rejected | W2 one-byte candidate and W3 binding tests | PASS |

## Filesystem and durable evidence

| Attack | Expected invariant | Proof | Result |
| --- | --- | --- | --- |
| Traversal, absolute/backslash paths, dot segments, NUL, controls or format characters | Workspace jail rejects before read or write | W1 path and character matrices | PASS |
| Hidden or secret-sensitive path | Closed artifact allowlist rejects it | W1 hidden/secret-sensitive matrix | PASS |
| Symlink, hardlink, FIFO, socket or device | Non-regular or aliased inode is rejected | W1 type tests and W3 unsafe-target matrix | PASS |
| Root/parent/target replacement or cross-workspace reference | Bound root, workspace and inode identity fail closed | W1 cross-workspace and W3 pre-replace swap tests | PASS |
| Unexpected file or directory | Exact tree proof detects tamper | W1 extra-file and W4 extra-file/directory tests | PASS |
| Oversized content or file-count overflow | Read/list bounds remain deterministic and preserve full digest evidence | W1 truncation and bounded-list tests | PASS |
| Malformed UTF-8 or ambiguous patch target | No proposal/effect is produced | W1 text contracts and W2 ambiguous-target tests | PASS |
| Base, supporting helper, runtime contract or proposal digest is changed | Proposal/apply validation rejects the mismatch | W2/W3 digest matrices | PASS |
| Authority envelope, effect receipt, report or terminal receipt is corrupted | Durable load/verification fails closed; no success is projected | W4 tamper tests and `test_corrupt_durable_authority_envelope_fails_closed_without_private_detail` | PASS |

## API, browser and presentation

| Attack | Expected invariant | Proof | Result |
| --- | --- | --- | --- |
| Unauthenticated call to any workspace route | Authentication precedes parsing/workflow dispatch | `test_every_workspace_hero_route_rejects_unauthenticated_access` | PASS |
| Cookie mutation lacks the exact intent header | Request is unauthorized | `test_cookie_authenticated_mutations_require_exact_browser_intent` | PASS |
| Wrong method, malformed/duplicate JSON, unknown field, wrong content type, header collision or oversized body | Bounded parser rejects before workflow execution | W6 method/JSON/body/header matrix | PASS |
| Stale/malformed run ID or path-ID confusion | No other run is selected and no effect occurs | W5 malformed/stale identity tests | PASS |
| Script/HTML is supplied through any dynamic display value | UI uses non-executable text sinks and strict CSP | W5 UI injection test and `test_judge_ui_uses_only_non_executable_dynamic_text_sinks` | PASS |
| Exception, private path, token, nonce, actor ID, cookie or environment value leaks | Error/projection remains bounded and sanitized | W5 projection tests plus W6 dependency/corruption tests | PASS |
| Refresh, back, duplicate click or stale tab | Durable projection is reconstructed and duplicate authority fails closed | W5 refresh/busy/replay tests | PASS |

## Recovery and dependencies

| Failure window | Expected invariant | Proof | Result |
| --- | --- | --- | --- |
| Crash before effect | Safely resumable; W4 cannot fabricate success | W4 crash-before-effect test | PASS |
| Crash after effect before receipt | Fresh read-back reconciles without reapplying | W3/W4 lost-receipt tests | PASS |
| Crash after receipt before verification | Verification runs; patch does not run again | W4 receipt-before-verify test | PASS |
| Crash after report before terminal receipt | Only the durable verified report permits receipt recovery | W4 terminal-receipt tests | PASS |
| Trusted verifier dependency is missing | State stays applied-unverified and errors reveal no private detail | `test_missing_verifier_dependency_cannot_leak_or_become_success` | PASS |
| Helper output/argv/mode/health/readiness is wrong, process exits or times out | Fixed profile reports failure and blocks terminal success | W4 fixed-profile and timeout matrices | PASS |
| Child attempts external egress | Loopback-only guard records zero external connections and blocks success | W4 profile and B4 network-egress proofs | PASS |

## Source, supply chain and claims

| Check | Bound | Proof | Result |
| --- | --- | --- | --- |
| Forbidden executable capability in workspace/hero source | No shell, arbitrary process, socket/client, eval/exec, dynamic import or URL-fetch capability | `test_workspace_and_hero_source_keep_forbidden_capabilities_out` | PASS |
| Direct dependency or lock drift | Direct runtime dependencies are exact pins and lock inputs match | `test_runtime_dependencies_and_lock_inputs_are_exactly_pinned` | PASS |
| Private build context/public staging input | Default-deny Docker context and tracked inventory exclude private runtime state | `test_container_context_and_tracked_inventory_exclude_private_runtime_state` | PASS |
| Secret/privacy material | Canonical scanner reports zero findings and emits no secret values | Final W6 canonical scan | PASS |
| Product wording | Live, locally proven, deterministic mock, optional and not implemented remain distinct | W6 audit and feature-freeze ledger | PASS |

## Confirmed defect and disposition

The red team confirmed that a durable hero run was not itself tied to the session that created it.
After a service restart with a different valid operator token, a second application composition
could reach the same durable approval request. W6 adds the originating `actor_session_id` to the
integrity-sealed run manifest and checks it for status, approval request, decision, resume and
verification. The regression test recreates the orchestrator after token rotation and proves a
`403` policy denial, unchanged `AWAITING_APPROVAL` state and zero workspace mutations.

No test, allowlist, verifier or approval binding was weakened to obtain this result.

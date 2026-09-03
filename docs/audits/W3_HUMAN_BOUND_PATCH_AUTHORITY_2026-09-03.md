# W3 human-bound exact patch authority — 2026-09-03

## Result

`W3_GATE=PASS` for the implementation and deterministic evidence at implementation anchor
`4281f420528c56cca375bd9470f827921572e71f` on branch
`codex/w3-human-bound-patch-authority`, subject to the final documentation commit and remote-ref
verification recorded at handoff.

W3 turns the exact W2 proposal into one durable human-bound, at-most-once file effect. The only
mutated object in the approve proof is `render.yaml` inside a disposable server-created
materialized workspace copy. Repository source, the tracked demo fixture, root `render.yaml`,
Render, AWS, DNS, provider resources, and paid resources were not mutated.

```text
MODEL_OUTPUT != EXECUTION_AUTHORITY
PATCH_PROPOSAL != PATCH_AUTHORITY
HUMAN_APPROVAL != VERIFIED_SUCCESS
PATCH_APPLIED != VERIFIED_SUCCESS
ACTION_ACKNOWLEDGEMENT != SUCCESS
```

The approve result is `PATCH_APPLIED_UNVERIFIED`; W3 emits no `SUCCESS_WITH_EVIDENCE`, verified
success, runtime-verification result, or deployment result.

## Certified base and W2 identity

| Fact | Value |
| --- | --- |
| required base branch | `codex/w2-structured-patch-proposal` |
| exact local/remote base HEAD | `2a3776fd91918056211625a91fe8c60ecbc7b8df` |
| W2 implementation anchor | `65e468e8d37061aaacb0b8a48d206ac773c78024` |
| W2 base ahead / behind | `0 / 0` |
| W2 audit gate / W3 readiness | PASS / YES |
| W2 reported full baseline | 1549/1549 |
| explicit W2 re-run | 34/34 |
| explicit W1 re-run | 50/50 |

The W3 certified proposal proof loads and validates the complete tracked W2 proposal rather than
hardcoding execution values. Its durable payload recomputes and retains:

| Identity | SHA-256 / value |
| --- | --- |
| W1 fixture root | `84172797b4203b01e7404649449ac7b6468e94b88e7aba9b2104d18c01668db8` |
| target before | `b957bbf10af3d711fbfeda271f8ba3b362894f4b02bb8d88239985769a3968db` |
| canonical after | `91eb20346909ca23779cdaf773586a9a925ebf59e90113615ecedcd24dc05314` |
| patch digest | `73be5422645433ca51371ab992854e028149c9a06753b61e1d66bfe5ed0ee5f0` |
| evidence digest | `4de8a59272f4f9cf57e2ad3c679897c2a9610d3fef858d0139268bb852ff6675` |
| proposal digest | `c9d9537e49e8388ba2ca5b92538383ca8c69d0d7fd2f704d2240002414736499` |
| startup script | `d350917c132a338605f630fde97a2ac017e1664fe9cf413a7153827326e6d250` |
| runtime contract | `8bf5a36539ea313a578e194e1c84568586770cc792d60709ebde106df9325178` |
| verification profile | `render_start_contract_v1` |
| risk | `PLAN_AND_CONFIRM` |

The deterministic W3 approval request hash is
`9f8a1a8d1d850059646e589cd7afea6f6d97a13fa5e8cb3e197b3a91ac4a99e1`.
It binds the full durable-proposal-derived human payload, including diff fingerprint, rollback,
version, expiry, and impact. It does not bind UI formatting or mutable model rationale.

## Authority reuse decision

W3 reuses one AIOA approval philosophy: proposal before approval, exact payload from durable truth,
canonical request hash, actor session, one-time nonce binding, interrupt/checkpoint before caller
return, decision before native resume, duplicate reconciliation, conflict rejection, and
write-before-effect ownership. It reuses the existing local integrity primitives and canonical
workspace hash convention.

Workspace facts remain in workspace-specific records. No `ActionTarget`, instance ID, EC2 state,
AWS capability, or `STOP_SANDBOX_INSTANCE` field is fabricated. No CloudOps source file was
modified. Exact reasoning and file boundaries are recorded in
`W3_AUTHORITY_REUSE_DECISION_2026-09-03.md`.

## Exact approval and native HITL

`WorkspaceApprovalPayload` is constructed only from a validated durable
`WorkspacePatchProposal`. It binds proposal/run/trace/workspace/fixture/base/target-before/after,
patch/evidence/support hashes, verification profile, rollback, version, expiry, risk, canonical
diff fingerprint, proposal digest, and fixed impact summary.

The external `WorkspaceApprovalResumeRequest` echoes the exact identities plus `decision`,
`actor_session_id`, and a bounded one-time `decision_nonce`. It has `extra=forbid` and no patch
content, arbitrary path, diff, command, argv, cwd, environment, verifier, provider, or deployment
field. Durable storage retains the nonce SHA-256 rather than plaintext. Identical decisions
reconcile to the original timestamp and hash; changed nonce or decision conflicts fail closed.

The W3 Strands profile has exactly six tools:

1. `inspect_deployment_incident`
2. `list_workspace_artifacts`
3. `read_workspace_artifact`
4. `hash_workspace_artifact`
5. `build_workspace_patch_proposal`
6. `apply_approved_workspace_patch`

The sixth schema has one required property, `proposal_id`. The native intervention creates a
`Confirm` only for a durably `AWAITING_APPROVAL` proposal and renders its prompt from durable
payload. `WorkspaceNativeApprovalFlow` persists the returned interrupt and request hash before
returning control. It persists the exact decision before native resume. Re-evaluation after resume
can proceed only from a durable approved decision; denial remains terminal.

## Durable repository and effect ordering

`LocalFileWorkspaceAuthorityRepository` stores a versioned strict snapshot in an owner-only
integrity envelope with a private lock, canonical SHA-256, process locking, private temporary
state, `fsync`, atomic replace, and directory `fsync`. Restarting with the same state path restores
the exact proposal, request, decision, ownership, receipt/marker, and audit timeline.

The closed state machine is:

```text
PATCH_PROPOSED -> AWAITING_APPROVAL
  -> DENIED_BY_HUMAN
  -> APPROVED -> APPLYING
     -> PATCH_APPLIED_UNVERIFIED
     -> RECONCILIATION_REQUIRED
```

`WorkspaceEffectOwnership` is atomically stored with `APPLYING` before the writable candidate is
created. Its idempotency key is derived from the exact proposal digest. There is no path from
missing/denied/conflicting approval to ownership or effect.

## Atomic replacement and receipt

The application-owned executor receives `proposal_id` only. It reloads all facts, checks proposal
expiry and exact approval, binds the materialized run/workspace/fixture/root, inspects the complete
allowlisted tree, requires a private single-link regular target, checks target-before and both
support hashes, and recomputes candidate-after and patch identity.

After ownership is durable, it repeats pre-effect validation, creates an owner-only hidden
same-directory file with `O_CREAT|O_EXCL|O_NOFOLLOW`, writes exactly
`proposal.preview.after_text`, sets the documented canonical target mode `0400`, flushes and
`fsync`s, and reopens the target immediately before replace. It uses one same-directory
`os.replace`, `fsync`s the directory, independently reopens/hashes the target, and compares the
complete before/after manifests. The success proof contains exactly one changed path:
`render.yaml`.

`PatchApplyReceipt` binds effect/idempotency/proposal/run/trace/workspace/fixture, target,
before/after/patch/request identities, post-root digest, and timestamps. Its strict literals are:

- `status=APPLIED_UNVERIFIED`
- `verification_required=true`
- `success_with_evidence=false`
- `verified_success=false`

## Denial, replay, and crash windows

| Scenario | Certified behavior |
| --- | --- |
| human deny | durable terminal `DENIED_BY_HUMAN`; 0 mutation, 0 ownership, 0 receipt |
| duplicate decision | identical record reconciles; nonce or decision conflict rejects |
| duplicate completed apply | same receipt returned; 0 extra mutation |
| approved before ownership | safe first apply after full revalidation |
| `APPLYING`, target before | same ownership may resume; exactly one eventual mutation |
| `APPLYING`, target after, no receipt | no reapply; `RECONCILIATION_REQUIRED` marker |
| `APPLYING`, unexpected target | no reapply; `RECONCILIATION_REQUIRED` marker |
| receipt before verification | no reapply; remains `PATCH_APPLIED_UNVERIFIED` for W4 |

Symlink, multi-link, FIFO/special target, base/target/support drift, cross-run/cross-workspace
decision, changed hashes/profile, TOCTOU target swap, unexpected path, expired proposal, unknown
tool, and expanded tool schema all fail closed with redacted errors.

## Mutation and capability accounting

| Proof | Result |
| --- | --- |
| approve workspace mutation count | 1 |
| approve changed paths | `render.yaml` |
| deny workspace mutation count | 0 |
| duplicate apply extra mutations | 0 |
| process executions by workspace flow | 0 |
| network connections by workspace flow | 0 |
| AWS calls / mutations | 0 / 0 |
| verified-success emissions | 0 |
| process / network / package / Git / browser-MCP tools | 0 / 0 / 0 / 0 / 0 |
| Render actions / deployments | 0 / 0 |
| paid resources | 0 |

Engineering commands used to run repository tests are certification activity, not a capability of
the workspace runtime. No patched workspace configuration was executed.

## Certification

| Gate | Result | Detail |
| --- | --- | --- |
| focused W3 | PASS | 62/62 |
| explicit W2 | PASS | 34/34 |
| explicit W1 | PASS | 50/50 |
| full pytest | PASS | 1611/1611 in 660.27 s |
| P0 | PASS | 15/15; 0 skipped |
| P1 | PASS | 6/6; 0 skipped |
| B4 | PASS | 11/11 scenarios; 43 proofs; 0 skipped |
| Ruff | PASS | full repository |
| pip check | PASS | no broken requirements |
| git diff check | PASS | no whitespace errors |
| canonical secret scan | PASS | 0 findings; 0 secret values emitted |
| clean-clone W1/W2/W3 | PASS | 146/146 |
| CloudOps HITL/replay/recovery | PASS | full regression plus focused historical gates |

The first concurrent P1 run reached 5/6 because P1-06 correctly rejected the then-dirty source
worktree while this audit was being authored. The canonical P1 gate was rerun from the clean final
documentation checkpoint and passed 6/6; this is a cleanliness control, not a product defect.

## Frozen deployment boundary

No B5/B6 recertification is required. W3 has no diff from W2 in repository-root `render.yaml`,
`Dockerfile`, `scripts/render_start.sh`, `pyproject.toml`, lock files, portable-server startup, or
CloudOps factory/HITL flows. Frozen hashes remain:

| Input | SHA-256 |
| --- | --- |
| root `render.yaml` | `c9e351188844ec4236068ffe62fa9747376ec520eabea39c9e92dd30909a645c` |
| `Dockerfile` | `4640463904ced78776f5f482510e9f117d7ee2e0b6a8e04c5ba83e349378bc8f` |
| `scripts/render_start.sh` | `d350917c132a338605f630fde97a2ac017e1664fe9cf413a7153827326e6d250` |
| `pyproject.toml` | `c11d0b6bc5a804599ecebed13753b16918d13d990735ab764cd9e000c08cfc5a` |
| `requirements/build.lock` | `d46492123b794c100b45c485f2981c1a12f71388f61439a5a662d850b19039a5` |
| `requirements/portable.lock` | `a7be92862cb66b67f2bf5b664f62abee1dbd48d65e2ee12fbcbaa5be2dff5dcd` |
| CloudOps `agent/factory.py` | `4f1b02661a1effab421b3ec6ed506bf50a97c17ca5eb66cf959d201e0a881822` |

Existing B5 `BUILD_COMPLETE` and B6 `PUBLICATION_READY` remain historical release evidence. W3 is
not wired into the public Render server and does not redeploy it.

## Evidence

- `docs/evidence/workspace/w3-approve-apply.json` — exact approval, ownership, single effect, and
  unverified receipt from the certified W2 proposal.
- `docs/evidence/workspace/w3-deny.json` — terminal denial, unchanged tree, no ownership/receipt.
- `docs/evidence/workspace/w3-replay-recovery.json` — duplicate and the three required crash
  windows, including both reconciliation markers.

All tracked receipts are sanitized. They contain no host path, operator token, plaintext decision
nonce, cloud account, deployment action, or provider resource identifier.

## Commit sequence

1. `e1c286f` — `docs(audit): decide workspace authority reuse boundary`
2. `39a42d7` — `feat(workspace): add exact human approval payload and durable binding`
3. `99c7da3` — `feat(workspace): add at-most-once atomic patch executor and receipt`
4. `c411294` — `feat(agent): add proposal-id-only workspace HITL apply tool`
5. `f0db3bd` — `test(workspace): certify approval replay crash and atomic-effect boundaries`
6. `4281f42` — `test(workspace): bind W3 evidence to certified W2 proposal`
7. final documentation checkpoint — `docs(workspace): freeze W3 human-bound patch authority checkpoint`

## Next safe step

`READY_FOR_W4_INDEPENDENT_VERIFICATION_RECOVERY=YES` means only that W3's unverified effect
checkpoint is certified. W4 requires a separate audited prompt. Do not run workspace processes or
tests, claim runtime success, deploy, mutate Render/AWS/DNS, broaden the tool surface, or continue
autonomously from this document.

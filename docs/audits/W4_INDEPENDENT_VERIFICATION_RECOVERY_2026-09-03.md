# W4 independent verification + recovery/reconciliation — 2026-09-03

## Result

`W4_GATE=PASS` for the implementation and deterministic evidence on branch
`codex/w4-independent-verification-recovery`, subject to the final clean documentation commit,
remote-ref verification, and push recorded at handoff.

W4 independently reopens the disposable workspace, proves the exact approved postcondition,
persists a content-addressed report, and only then persists the receipt that permits
`SUCCESS_WITH_EVIDENCE`. It never treats the human decision, effect ownership, executor receipt,
process exit, HTTP status, or model output as verified truth.

```text
MODEL_OUTPUT != EXECUTION_AUTHORITY
HUMAN_APPROVAL != VERIFIED_SUCCESS
PATCH_APPLIED != VERIFIED_SUCCESS
EXECUTOR_RECEIPT != VERIFIED_SUCCESS
ACTION_ACKNOWLEDGEMENT != SUCCESS
```

## Certified W3 base

| Fact | Value |
| --- | --- |
| base branch | `codex/w3-human-bound-patch-authority` |
| exact local/remote base HEAD | `8827cf9943361c30b3c116e25895f0b99855149e` |
| base ahead / behind | `0 / 0` |
| W3 gate / W4 readiness | PASS / YES |
| W3 terminal effect state | `PATCH_APPLIED_UNVERIFIED` |
| W3 verified-success emissions | 0 |
| W3 deny mutations | 0 |
| W3 duplicate-apply extra mutations | 0 |
| W3 process / AWS calls / AWS mutations | 0 / 0 / 0 |
| W3 reported full baseline | 1611/1611 |
| explicit W3 re-run | 62/62 |
| explicit W2 re-run | 34/34 |
| explicit W1 re-run | 50/50 |

The W4 branch was created only after fetching origin, parsing the tracked W3 report, matching the
local and remote W3 HEAD exactly, confirming a clean worktree, and rechecking the frozen deployment
hashes.

## Independent read-back

`WorkspaceVerificationBoundary` maps only the durable workspace ID to a private server-owned root
and trusted fixture source. On every call it performs a fresh descriptor-confined scan and:

- reopens the mapped root instead of using executor-returned content;
- rechecks root device, inode, owner, type, and mode;
- rescans the trusted base fixture and recomputes its canonical digest;
- opens files with no-follow semantics and verifies owner, regular-file type, single link, size,
  mode, and stable metadata around the read;
- detects created, removed, modified, type-changed, linked, and unexpected entries;
- recomputes the current artifact set and root digest from disk.

The canonical evidence proves exactly one changed path, `render.yaml`; its actual SHA-256 equals
the approved canonical-after hash. The old folded inline `dockerCommand` is absent, the fixed
`/usr/local/bin/aioa-render-start` entry occurs once, and the startup script plus expected runtime
contract remain byte-identical to their W2 bindings.

## Executor receipt is not truth authority

The W3 `PatchApplyReceipt` is strictly revalidated and content-addressed only as an effect-evidence
reference. Its claims do not determine any W4 check. Tests retain a valid executor receipt while
changing the target, a support file, or the artifact set; every case blocks success based on fresh
disk evidence. A tampered receipt identity fails before verification.

The tracked evidence deliberately keeps these separate:

1. approved effect identity;
2. unverified executor receipt;
3. optional recovery observation;
4. independent verification report;
5. terminal verification receipt and state.

## Trusted `render_start_contract_v1` profile

The model can supply only `proposal_id`; it cannot select a command, argv, cwd, environment,
executable, path, URL, port, timeout, profile, or expected value. The fixed no-argument helper under
`scripts/w4_render_start_profile.py` owns all of those facts. Keeping explicit process/network
imports outside `src/aioa_cloudops_agent` preserves the existing CloudOps
no-shell/no-arbitrary-network-client source guard without adding an exception.

One canonical probe:

- proves missing bootstrap token fails closed before process launch;
- writes a synthetic token to an owner-only `0600` file;
- removes `AIOA_OPERATOR_TOKEN` from the child environment;
- launches only `python -m aioa_cloudops_agent.portable_server`;
- binds loopback host and an ephemeral port;
- uses portable mode, mock provider, AWS disabled, fixed timeouts, and bounded logs/responses;
- obtains the exact healthy `/health` and ready `/ready` contracts;
- installs a trusted child guard that records and denies non-loopback socket attempts;
- reports zero external egress attempts and zero AWS calls.

It executes no script, Python module, test, `conftest.py`, or Git hook from the sealed workspace.
The process is verifier-internal and is not a registered agent capability.

| Counter | Value |
| --- | --- |
| model process capabilities registered | 0 |
| fixed verifier process probes per canonical verification | 1 |
| workspace code executions | 0 |
| arbitrary command executions | 0 |
| verifier external egress | 0 |
| verifier AWS calls | 0 |

## Durable verification order

The W3 repository is extended, not replaced. Its single state record now supports:

```text
PATCH_APPLIED_UNVERIFIED / recovered exact effect
  -> VERIFYING
     -> SUCCESS_WITH_EVIDENCE
     -> VERIFICATION_FAILED
     -> RECONCILIATION_REQUIRED
     -> DEPENDENCY_UNAVAILABLE
```

`WorkspaceVerificationReport` binds proposal/run/trace/workspace/fixture/effect, patch, base,
expected and actual after hashes, expected and actual changed paths, support hashes, fixed profile,
effect proof reference, ordered checks, time, disposition, and report digest. Its nineteen checks
must have the canonical enum order.

The repository first persists that report. `WorkspaceVerificationReceipt` can then be created only
from a durable `VERIFIED` report with matching effect and observed state. Only persisting that
receipt transitions the same proposal record to `SUCCESS_WITH_EVIDENCE`. A direct terminal-receipt
attempt before the report is rejected.

Canonical tracked identities:

| Identity | SHA-256 / value |
| --- | --- |
| W2 proposal digest | `c9d9537e49e8388ba2ca5b92538383ca8c69d0d7fd2f704d2240002414736499` |
| patch digest | `73be5422645433ca51371ab992854e028149c9a06753b61e1d66bfe5ed0ee5f0` |
| target before | `b957bbf10af3d711fbfeda271f8ba3b362894f4b02bb8d88239985769a3968db` |
| target after | `91eb20346909ca23779cdaf773586a9a925ebf59e90113615ecedcd24dc05314` |
| post-effect root | `37db9e24ae3c34de91d3efc91453131871dfecbe74b513e235ab05ba368408e3` |
| executor receipt digest | `a90cf040dcec09b19f8d46c22c56096ce350608ca11b4ccf50c391885adffb01` |
| independent report digest | `a997dc6137fa7799aca45cf493fad00e24e906360a2367eb6e7adc64eb87b5ee` |
| terminal receipt digest | `3df3a244d0ee74bc58133f1feaeb4766d91d392dcf3927f0e6673a814727facc` |

## Recovery and reconciliation

| Window | W4 result | Second patch apply |
| --- | --- | --- |
| crash before effect; exact BEFORE | `SAFE_RESUMABLE_FOR_W3_APPLY`; W4 stops | 0 |
| crash after effect before receipt; exact AFTER only | distinct `RECOVERY_READ_BACK`, then verify | 0 |
| W3 lost-receipt marker; exact AFTER only | marker plus fresh read-back reconciled, then verify | 0 |
| receipt durable before verification | skip apply; verify only | 0 |
| neither exact BEFORE nor exact AFTER | `RECONCILIATION_REQUIRED` | 0 |
| extra or unsafe artifact | mismatch/reconciliation; no rollback | 0 |
| duplicate verification | reuse report/receipt; zero additional probe | 0 |
| tampered report digest | reject | 0 |

No missing executor receipt is fabricated. Recovery evidence has its own ID, digest, classification,
and observed state.

## Exact tool surface

The W4 Strands profile has exactly seven tools:

1. `inspect_deployment_incident`
2. `list_workspace_artifacts`
3. `read_workspace_artifact`
4. `hash_workspace_artifact`
5. `build_workspace_patch_proposal`
6. `apply_approved_workspace_patch`
7. `verify_workspace_remediation`

The seventh schema has one required field, `proposal_id`. It is `AUTO` only after the deterministic
controller proves exact approval/effect eligibility. The sixth remains native-HITL protected.
There is no arbitrary process, shell, network, package, Git, browser, MCP, URL, or host-path tool.
The canonical CloudOps tool surface and historical W1/W2/W3 factories are unchanged.

## Certification

| Gate | Result | Detail |
| --- | --- | --- |
| focused W4 | PASS | 37/37 |
| explicit W3 | PASS | 62/62 |
| explicit W2 | PASS | 34/34 |
| explicit W1 | PASS | 50/50 |
| full pytest | PASS | 1648/1648 in 698.71 s |
| P0 | PASS | 15/15; 0 skipped |
| P1 | PASS | 6/6; 0 skipped |
| B4 | PASS | 11/11 scenarios; no weakened semantics |
| Ruff | PASS | full repository |
| pip check | PASS | no broken requirements |
| git diff check | PASS | no whitespace errors |
| canonical secret scan | PASS | 0 findings; 0 secret values emitted |
| clean-clone W1/W2/W3/W4 | PASS | 183/183 |
| CloudOps source guard | PASS | no shell/arbitrary network client in canonical `src` |

The first full regression reached 1647/1648. The one failure correctly detected W4's initial
`socket`/`subprocess` imports inside canonical `src`. The fixed helper was moved under `scripts/`,
the guard itself was not changed or allowlisted, focused W4 remained 37/37, and the canonical full
rerun passed 1648/1648.

## Frozen deployment boundary

W4 does not change repository-root deployment/publication inputs. Frozen hashes remain:

| Input | SHA-256 |
| --- | --- |
| root `render.yaml` | `c9e351188844ec4236068ffe62fa9747376ec520eabea39c9e92dd30909a645c` |
| `Dockerfile` | `4640463904ced78776f5f482510e9f117d7ee2e0b6a8e04c5ba83e349378bc8f` |
| `scripts/render_start.sh` | `d350917c132a338605f630fde97a2ac017e1664fe9cf413a7153827326e6d250` |
| `pyproject.toml` | `c11d0b6bc5a804599ecebed13753b16918d13d990735ab764cd9e000c08cfc5a` |
| `requirements/build.lock` | `d46492123b794c100b45c485f2981c1a12f71388f61439a5a662d850b19039a5` |
| `requirements/portable.lock` | `a7be92862cb66b67f2bf5b664f62abee1dbd48d65e2ee12fbcbaa5be2dff5dcd` |
| CloudOps `agent/factory.py` | `4f1b02661a1effab421b3ec6ed506bf50a97c17ca5eb66cf959d201e0a881822` |

Therefore `B5_B6_RECERTIFICATION_REQUIRED=NO`. W4 performed 0 Render actions, 0 AWS calls, 0 AWS
mutations, 0 external deployments, and created 0 paid resources.

## Evidence and limitations

- `docs/evidence/workspace/w4-verification-report.json` is the sanitized deterministic canonical
  report and receipt bound to the certified W3/W2 identity.
- W4 verifies only the private sealed fixture and fixed remediation profile. It is not wired to the
  public portable server and is not a live Render deployment claim.
- The process proof requires Linux `/proc` and repository-checkout access to the fixed helper. It
  fails closed if those trusted dependencies are unavailable.
- The server-owned mapping assumes an unprivileged same-user threat boundary; it does not claim
  containment from a host-root attacker.

## Commit sequence

1. `5ab9c6f` — `feat(verification): add independent workspace verification contracts`
2. `7060a6d` — `feat(verification): implement render-start trusted verification profile`
3. `349b762` — `feat(recovery): reconcile workspace patch crash windows by read-back`
4. `b16e0fa` — `feat(agent): expose bounded workspace verification tool`
5. final test checkpoint — `test(verification): certify W4 proof and no-replay boundaries`
6. final documentation checkpoint — `docs(verification): freeze W4 verification checkpoint`

## Exact gate fields

```text
W3_GATE_REVERIFIED=PASS
INDEPENDENT_REOPEN=PASS
EXECUTOR_RECEIPT_NOT_TRUSTED_AS_TRUTH=PASS
EXACT_CHANGED_PATH_SET=PASS
TARGET_AFTER_HASH=PASS
SUPPORTING_ARTIFACTS_UNCHANGED=PASS
TRUSTED_VERIFICATION_PROFILE=PASS
TOKEN_MODE_0600_PROOF=PASS
BOOTSTRAP_SECRET_REMOVED_FROM_CHILD_ENV=PASS
HEALTH_CHECK=PASS
READINESS_CHECK=PASS
NO_WORKSPACE_CODE_EXECUTION=PASS
VERIFICATION_EVIDENCE_PERSISTED=PASS
SUCCESS_WITH_EVIDENCE_GATED=PASS
RECOVERY_AFTER_EFFECT_BEFORE_RECEIPT=PASS
RECOVERY_AFTER_RECEIPT_BEFORE_VERIFY=PASS
DUPLICATE_VERIFY_RECONCILES=PASS
NO_SECOND_PATCH_APPLY=PASS
W4_GATE=PASS
READY_FOR_W5_JUDGE_HERO_INTEGRATION=YES
```

## Next safe step

Stop W4. Do not merge, deploy, mutate Render/AWS/DNS, or continue autonomously. W5 judge/hero
integration requires its own audited prompt.

# W5 judge hero workflow + UI integration — 2026-09-03

## Result

`W5_GATE=PASS` for the source implementation certified on branch
`codex/w5-judge-hero-integration`. The implementation checkpoint before this audit is
`a5cc6b0d401fe4c0f49ad3ea739e19b0d6549b94`; the exact pushed checkpoint is recorded in the
phase handoff.

The existing authenticated Local-2 judge application now presents one fixed, deterministic story:

```text
Observe -> Evidence -> Root Cause -> Exact Patch -> Policy -> Human Decision
        -> Execute Once -> Independent Verify -> Receipt -> Replay Rejected
```

The UI copy states the governing truth directly: **The model proposes. The human authorizes.
Evidence decides.** Human approval does not mean success, and a patch effect remains
`PATCH_APPLIED_UNVERIFIED` until the existing W4 independent verifier persists both its report and
terminal receipt.

## Certified base and frozen boundary

| Fact | Value |
| --- | --- |
| certified base branch | `codex/w4-independent-verification-recovery` |
| exact base HEAD | `4f021ddb69d6f5e83a94f8e17b951dd3a2c8f5dc` |
| base W4 gate | PASS |
| historical W4 full baseline | 1648/1648 |
| explicit W4 / W3 / W2 / W1 re-runs | 37/37, 62/62, 34/34, 50/50 |
| feature branch | `codex/w5-judge-hero-integration` |
| fixed scenario ID | `FAILED_RENDER_DEPLOYMENT_VERIFIED_FIX_V1` |
| Render actions / AWS calls / AWS mutations | 0 / 0 / 0 |
| paid resources | 0 |

Repository-root deployment files were not changed. Their hashes remain:

| Input | SHA-256 |
| --- | --- |
| `render.yaml` | `c9e351188844ec4236068ffe62fa9747376ec520eabea39c9e92dd30909a645c` |
| `Dockerfile` | `4640463904ced78776f5f482510e9f117d7ee2e0b6a8e04c5ba83e349378bc8f` |
| `scripts/render_start.sh` | `d350917c132a338605f630fde97a2ac017e1664fe9cf413a7153827326e6d250` |
| `pyproject.toml` | `c11d0b6bc5a804599ecebed13753b16918d13d990735ab764cd9e000c08cfc5a` |
| `requirements/build.lock` | `d46492123b794c100b45c485f2981c1a12f71388f61439a5a662d850b19039a5` |
| `requirements/portable.lock` | `a7be92862cb66b67f2bf5b664f62abee1dbd48d65e2ee12fbcbaa5be2dff5dcd` |

W5 does change judge/runtime application code. Therefore historical B5/B6 PASS evidence is retained
as historical evidence only, and `FINAL_RC_B5_B6_RECERTIFICATION_REQUIRED=YES` before a new image or
public bundle can claim W5.

## Additive API and authority composition

The existing CloudOps route behavior remains intact. W5 adds only this fixed route family:

1. `POST /api/workspace-demo/runs`
2. `GET /api/workspace-demo/runs/{run_id}`
3. `POST /api/workspace-demo/runs/{run_id}/approval-request`
4. `POST /api/workspace-demo/runs/{run_id}/decision`
5. `POST /api/workspace-demo/runs/{run_id}/resume`
6. `POST /api/workspace-demo/runs/{run_id}/verify-or-reconcile`

The small `WorkspaceHeroOrchestrator` composes the certified W1-W4 services. It does not recreate
proposal, approval, apply, verification, or replay authority. The server owns the scenario,
workspace mapping, patch, target, proposal identity, verifier profile, approval request, and durable
state. The browser sends only the human decision and the currently displayed request fingerprint;
the decision nonce is derived and consumed server-side.

No direct mutation, raw file-write/path, arbitrary command/process, URL-fetch, package-install, Git
mutation, browser, MCP, or AWS capability was added. The fixed W4 process probe remains
verifier-internal and is loaded from the already-certified no-argument helper
`scripts/w4_render_start_profile.py`.

## Bounded judge projection and UX

The browser receives a strict, bounded projection with ten typed stages:

1. `OBSERVE`
2. `EVIDENCE`
3. `ROOT_CAUSE`
4. `PATCH_PROPOSAL`
5. `POLICY`
6. `HUMAN_DECISION`
7. `PATCH_EFFECT`
8. `VERIFICATION`
9. `RECEIPT`
10. `RECOVERY_REPLAY`

The approval card is built from durable W2/W3 facts and displays the exact target, field, change,
workspace/proposal/patch fingerprints, evidence set, verification profile and checks, risk,
rollback, and the one-proposal warning. The W2 unified diff is display-only. Executor evidence and
independent verifier evidence are visually distinct; applied-but-unverified is never rendered as
green final success.

Projection contracts expose no operator token, session token, decision nonce, actor-session ID,
synthetic child token, private temporary path, stack trace, or cookie. Text is inserted with
`textContent`, the page retains strict CSP and no browser storage is used. Shared busy state,
focus-visible styling, 44 px controls, reduced-motion behavior, and sub-700 px layout rules are
covered by the focused UI contract tests.

## End-to-end evidence

| Journey | Result | Effect accounting |
| --- | --- | --- |
| approve | `SUCCESS_WITH_EVIDENCE` | exactly 1 workspace mutation and 1 patch apply |
| deny | `DENIED_BY_HUMAN` | 0 mutations, no executor or verifier receipt |
| replay | `REPLAY_REJECTED_RECONCILED` | 0 additional mutations and 0 additional profile executions |
| refresh | authoritative state reconstructed | same fingerprints, 0 duplicate effects |
| stale/cross-run request | fail closed | 0 unauthorized effects |

Recovery is shown from the certified W4 receipt/timeline contract. W5 deliberately does not add an
artificial destructive browser crash. The separate W4 suite remains the executable recovery proof,
including crash-after-effect reconciliation without a second patch apply.

No public-safe screenshots were captured because an isolated browser harness was not available for
this checkpoint. No user Chrome session was accessed. Responsive, injection, busy-state, refresh,
and complete API journey behavior is covered by deterministic integration tests; screenshots remain
optional UX reference evidence and are not substituted for authority tests.

## Certification

| Gate | Result | Detail |
| --- | --- | --- |
| focused W5 API/UI/E2E | PASS | 28/28 |
| explicit W4 | PASS | 37/37 |
| explicit W3 | PASS | 62/62 |
| explicit W2 | PASS | 34/34 |
| explicit W1 | PASS | 50/50 |
| focused source security + Local API/UI + W5 | PASS | 55/55 |
| full pytest | PASS | 1676/1676 in 693.01 s |
| P0 | PASS | 15/15; 136 proof cases; 0 skipped |
| P1 | PASS | 6/6; 93 proof cases; 0 skipped |
| B4 | PASS | 11/11; 43 proof tests |
| Ruff | PASS | full repository |
| pip check | PASS | no broken requirements |
| git diff check | PASS | no whitespace errors |
| canonical secret scan | PASS | 473 files; 0 findings; 0 secret values |
| clean-clone focused hero | PASS | exact source checkpoint; 28/28 |

The B4 receipt and canonical secret scan record zero AWS calls/mutations, external egress, and
external deployments. The secret-scan receipt SHA-256 is
`8f882bcb140d26f2cebdf5e1c953c44501e33b3db516114abd733a8c98a4d58d`.

The first full W5 regression reached 1673/1676 because three documentation/manifest assertions
correctly detected the changed Local-2 authority. The authority was re-anchored to the immutable W5
implementation checkpoint `6b4c294a0d91ed7ba5ee2f84235f74621f11e5ad`. The second full run also
reached 1673/1676 because the historical B5 builder was comparing an evolving current-worktree
reviewer manifest to a frozen source commit. The builder now derives that one evolving manifest hash
from the historical source commit while retaining current-worktree comparison for all frozen B5
inputs. Tracked B5 artifacts remain byte-identical and do not claim W5 recertification. The final
full run passed 1676/1676.

## Evidence and limitations

- `docs/evidence/workspace/w5-judge-hero.json` is the sanitized deterministic hero evidence.
- This is a local/portable mock scenario, not a live Render deployment or live AWS remediation.
- W5 is a fixed remediation experience, not an arbitrary coding, process, filesystem-write, browser,
  MCP, Git, package-install, or URL-fetch interface.
- The source-checkout W5 verifier reuses the exact certified W4 helper under `scripts/`. A future
  release candidate must package and certify that helper without weakening the canonical source
  guard; the required full B5/B6 recertification is intentionally outside W5.
- The existing same-user workspace isolation boundary is preserved; no host-root containment or
  production multi-user security claim is made.
- Hosted durable recovery on Render Free is not claimed.

## Commit sequence before final audit checkpoint

1. `3ad1b1f` — `feat(judge): add fixed workspace hero API composition`
2. `d485ba4` — `feat(judge): add evidence-bound remediation hero UI`
3. `8004576` — `test(judge): certify hero authority and replay journeys`
4. `f36cc09` — `fix(judge): reuse certified W4 trusted profile`
5. `ac89c2f` — `test(judge): bind hero success to certified W4 profile`
6. `6b4c294` — `docs(judge): document W5 hero product experience`
7. `edc837b` — `docs(evidence): reanchor Local-2 authority to W5`
8. `a5cc6b0` — `fix(evidence): preserve source-bound historical B5 outputs`

## Exact gate fields

```text
W4_BASE_VERIFIED=PASS
HERO_SCENARIO_EXPOSED=PASS
AUTHENTICATED_JUDGE_FLOW=PASS
EXACT_APPROVAL_CARD=PASS
PATCH_DIFF_VISIBLE=PASS
BEFORE_AFTER_PROOF_VISIBLE=PASS
VERIFICATION_RECEIPT_VISIBLE=PASS
DENY_FLOW_VISIBLE=PASS
REPLAY_REJECTION_VISIBLE=PASS
REFRESH_RESTORE=PASS
NO_DIRECT_MUTATION_ENDPOINT=PASS
NO_SECRET_EXPOSURE=PASS
MOBILE_DESKTOP_UX=PASS
HERO_E2E_APPROVE=PASS
HERO_E2E_DENY=PASS
HERO_E2E_REPLAY=PASS
FINAL_RC_B5_B6_RECERTIFICATION_REQUIRED=YES
HISTORICAL_B5_B6_EVIDENCE_PRESERVED=YES
DEPLOYMENT_FILES_CHANGED=NO
RENDER_ACTIONS=0
AWS_CALLS=0
AWS_MUTATIONS=0
PAID_RESOURCES_CREATED=0
W5_GATE=PASS
READY_FOR_W6_SECURITY_FEATURE_FREEZE=YES
```

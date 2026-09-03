# W6 security red-team and feature-freeze audit — 2026-09-03

## Candidate result

The W6 source fix and adversarial suite are complete. `W6_GATE` remains
`PENDING_FINAL_CERTIFICATION` until the clean committed candidate completes full pytest, P1, B4,
Ruff, pip check, canonical secret scan and clean-clone hero proof.

## Proven starting point

| Fact | Value |
| --- | --- |
| required W5 branch | `codex/w5-judge-hero-integration` |
| exact local/remote W5 HEAD | `484ccf1af3a3001c2146fea7d4459a6feb6bf9d1` |
| ahead / behind | `0 / 0` |
| W5 gate / W6 readiness | `PASS / YES` |
| starting worktree | clean |
| W6 branch | `codex/w6-security-feature-freeze` |
| main observed at preflight | `4fafed8b1a877e55d96ddd9baea0a737fbeeaa4a` |
| deployment branch observed at preflight | `03d1c8f6a1d254c98c0b4e88fc93e25ea85ed4c7` |

Deployment inputs, dependency locks, CloudOps factory, W1-W5 evidence and the Local-2 public
surface were hashed before changes. The complete W1-W5 evidence snapshot is retained in Git; the
deployment/lock hashes are recorded in `docs/evidence/workspace/w6-red-team.json`.

## Confirmed P0 defect and correction

The hostile-session test found one real authority defect. The W3 decision record bound whichever
authenticated actor made a decision, but the W5 run manifest did not bind the run to the actor that
created it. A process restart with a rotated valid token could therefore construct a new Local API
application over the existing run and consume its awaiting request.

W6 changes only the hero composition boundary:

- the integrity-sealed manifest now stores the originating `actor_session_id`;
- start requires an authenticated principal;
- status, approval request, decision, resume and verify/reconcile compare the authenticated
  principal to the durable originating session using constant-time comparison;
- mismatch returns a sanitized `403` policy denial before authority/effect work;
- the regression recreates the orchestrator with a different valid token and proves unchanged
  `AWAITING_APPROVAL`, zero mutation and zero verifier calls.

No W3/W4 authority rule, verifier, allowlist or test was weakened. Existing manifests lacking the
new required identity fail closed.

## Red-team scope and result

`docs/security/W6_ATTACK_MATRIX.md` maps the complete attack program to executable proof. It covers
authority smuggling, stale/replayed/cross-session decisions, pre-effect drift, concurrent tabs and
conflicting decisions; filesystem traversal/types/identity/TOCTOU/bounds; API parsing and browser
injection; durable-evidence corruption; crash windows and verifier failures; forbidden source
capabilities, dependency pins, Docker context and public-claim truth.

The new suite contributes 50 cases. The explicit retained W5/W4/W3/W2/W1 suites contribute
28/37/62/34/50 cases and pass as one 211-test regression.

## Feature-freeze decision

`docs/security/FEATURE_FREEZE.md` is authoritative for W7/W8. The fixed workspace hero, exact
proposal, human-bound apply, independent verification, recovery/replay and legacy deterministic
CloudOps judge path remain. Live AWS in the core demo, personal-browser integration, hosted
multi-user claims and generic coding/shell/file/Git/package/browser/MCP authority are cut or
explicitly not implemented.

W7/W8 may package, harden, certify and document. They may not add product capability.

## Candidate certification ledger

| Gate | Result |
| --- | --- |
| new W6 adversarial suite | PASS — 50/50 |
| explicit W5 / W4 / W3 / W2 / W1 | PASS — 28/28, 37/37, 62/62, 34/34, 50/50 |
| reviewer evidence manifest | PASS — 120/120 tests, 28 claims, 0 live receipts |
| P0 | PASS — 15/15, 136 proof cases, 0 skipped |
| P1 | PENDING FINAL CLEAN-CHECKPOINT RUN |
| B4 | PENDING FINAL RUN |
| full pytest | PENDING FINAL RUN |
| Ruff / pip check / diff check | PENDING FINAL RUN |
| canonical secret scan | PENDING FINAL RUN |
| clean-clone focused hero | PENDING FINAL RUN |

## Truth and external-action boundary

- This is locally proven and mock/deterministic evidence, not a live W6 deployment.
- Historical Render evidence does not prove this source candidate.
- Final B5/B6 recertification is required in W7 because runtime authority changed.
- Render actions, external deployments, AWS calls, AWS mutations, DNS actions and paid resources
  during W6 are all zero.
- No personal browser, cookie, email, publication, submission, tag, main merge, force push or branch
  deletion occurred.

## Candidate commit sequence

1. `7fe3266` — `fix(judge): bind hero runs to operator sessions`
2. `4d133aa` — `test(security): prove token rotation fails closed`
3. `5d36d28` — `docs(evidence): reanchor Local-2 authority to W6`

The exact final pushed W6 HEAD is recorded after the closing audit commit to avoid a self-referential
commit claim.

## Pending exact gate fields

```text
W6_NEW_TESTS=50/50
W6_EXPLICIT_W5_W4_W3_W2_W1=28/28,37/37,62/62,34/34,50/50
W6_P0=PASS_15_OF_15
W6_P1=PENDING_FINAL_GATE
W6_B4=PENDING_FINAL_GATE
W6_FULL_TESTS=PENDING_FINAL_GATE
W6_SECRET_SCAN=PENDING_FINAL_GATE
W6_UNRESOLVED_P0_BLOCKERS=0
FEATURE_FREEZE=PENDING_FINAL_GATE
W6_GATE=PENDING_FINAL_CERTIFICATION
```

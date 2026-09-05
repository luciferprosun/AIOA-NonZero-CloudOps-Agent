# W7A Phase 8 — Deterministic Git/GitHub Write Actuator

Date: 2026-09-05 Europe/Berlin

Work branch: `codex/w7a-agent-execution-slice`

Phase 7 checkpoint: `e4b6de4b7dd9d5145c6277a4b1b17eae6a9b3f27`

Frozen W7/B5/B6 head: `945c87052815b237004d259fe993cc92cbd579b7`

## Result

`PHASE_8_RESULT=PARTIAL_HUMAN_AUTHORITY_REQUIRED`.

The deterministic actuator, strict contracts, integrity-sealed effect repository,
canonical GitHub HTTPS adapter, local bare-remote proof adapter, and rootless-Docker
verification adapter are implemented. Focused unit and integration tests exercise
the complete effect algorithm locally. No exact durable human decision exists for
a finalized live GitHub capsule, so the live product mutation was correctly not
attempted and Phase 9 is prohibited.

The required live remote receipt does not exist. The only receipt in Phase 8
evidence is explicitly scoped to a disposable local bare remote and cannot satisfy
the live GitHub gate.

## Security order and reuse

The actuator composes, rather than replaces, the Phase 5 `BoundedPatchSetPolicy`,
Phase 6 repair-loop and Docker validation primitives, Phase 7 capsule/authority
validator, canonical JSON hashing, UUIDv7 identifiers, and the existing locked,
owner-only integrity-envelope persistence pattern.

The enforced order is:

1. independent read-only repository/default/base/target observation;
2. load and validate the durable exact human decision;
3. deny identity/default/base/target/PatchSet ambiguity;
4. clone the exact base into a disposable owner-controlled worktree;
5. recheck the bounded Phase 5 base/final workspace, materialize only approved
   paths, re-hash every result, and prove the staged path set is exact;
6. require a credential-free, network-none verification receipt (with a concrete
   rootless Docker adapter for production wiring);
7. build a deterministic commit and independently check its materialized files;
8. fsync durable semantic effect ownership before any remote attempt;
9. expose a write credential only as a Git child-process extra header, never in
   argv, diagnostics, evidence, worker, sandbox, test or MCP state;
10. push one internally formed non-force feature ref;
11. classify timeout/lost acknowledgement as `UNKNOWN`;
12. independently read the remote ref/commit/tree. Only an exact match emits a
   success receipt; otherwise durable reconciliation blocks blind retry.

The full Git repository may contain more than the Phase 5 bounded workspace limit.
The actuator therefore rechecks the exact Phase 5 source/final workspace while
validating approved before/after identities in the full Git clone. A focused test
proves a one-file bounded PatchSet against a remote containing more than 300
unrelated files; no whole-repository policy weakening was introduced.

## Closed negative matrix

- default/main, non-AIOA namespace, `refs/` alias, wildcard and traversal targets:
  denied;
- force, tag, merge and generic refspec APIs: absent;
- remote identity/default/base drift and pre-existing target: denied before write;
- missing, expired, mismatched or replayed authority: denied;
- changed PatchSet/final bytes and verification crash: denied before ownership;
- symlink, hardlink, special file and path traversal: denied;
- target change between initial and final precondition: denied;
- lost ACK with matching readback: safely reconciled to verified;
- lost ACK without matching readback: durable `UNKNOWN`, no blind second push;
- completed operation replay: denied, write-attempt count remains one;
- GitHub MCP: byte-for-byte unchanged and still read-only.

## Credential custody and mutation truth

```text
WORKER_GITHUB_WRITE_CREDENTIALS=0
SANDBOX_GITHUB_WRITE_CREDENTIALS=0
TEST_PROCESS_GITHUB_WRITE_CREDENTIALS=0
WORKER_AWS_CREDENTIALS=0
SANDBOX_AWS_CREDENTIALS=0
WORKER_SSH_CREDENTIALS=0
WRITE_ACTUATOR_CREDENTIAL_SCOPE=MINIMUM_REQUIRED
TOKEN_VALUES_IN_LOGS=0
TOKEN_VALUES_IN_EVIDENCE=0
LOCAL_BARE_REMOTE_TEST_WRITES=bounded disposable fixtures only
PRODUCT_RUNTIME_GITHUB_WRITES=0
DEFAULT_BRANCH_WRITES=0
FORCE_PUSHES=0
TAG_WRITES=0
MERGES=0
AWS_CALLS=0
AWS_MUTATIONS=0
DEPLOYMENTS=0
```

## Gate and blocker

Focused Phase 8 tests: `28/28 PASS` (21 unit, 7 integration). Static, secret and
diff checks are recorded at checkpoint closure. Existing Phase 4 and Phase 6
rootless-Docker certification remains the runtime foundation; this partial phase
does not relabel a synthetic verifier as a live sandbox receipt.

```text
PHASE_7_REGRESSION=29/29 PASS
RUFF=PASS
PIP_CHECK=PASS
SECRET_SCAN=PASS (568 files, 0 findings)
SECRET_SCAN_RECEIPT=55f9ad26beca3410188a6861fd98147209e210107bfb57bab5ff3824b3f5530d
GIT_DIFF_CHECK=PASS
```

The review artifact is
`docs/evidence/w7a/phase8-human-approval-request.json`. It deliberately marks the
tested capsule as local-fixture-only. A human must first select/finalize the exact
live PatchSet/base/branch, regenerate a current Phase 6-backed capsule, and persist
an exact approval decision. This PDF is not that decision.

```text
PHASE_8_FOCUSED=28/28 PASS
LOCAL_BARE_REMOTE_PROOF=PASS
DURABLE_OWNERSHIP_BEFORE_WRITE=PASS
LOST_ACK_RECONCILIATION=PASS
BLIND_RETRY=DENY
LIVE_HUMAN_APPROVAL_BOUND=NO
LIVE_REMOTE_WRITE_RECEIPT=NOT_CREATED
PHASE_8_RESULT=PARTIAL_HUMAN_AUTHORITY_REQUIRED
PHASE_9_AUTHORIZED=NO
```

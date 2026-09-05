# W7A Phase 6 — Finite Offline Test, Repair and Review Loop

Prompt date: 2026-09-04 UTC

Certification completed: 2026-09-05 UTC

Work branch: `codex/w7a-agent-execution-slice`

Phase 5 checkpoint: `19e6a9be8ed6fff93a359fbdd9792c66de0f302d`

Phase 6 implementation commit: `88d41b1721914f13588319883c85656953b1bf2a`

Frozen W7/B5/B6 head: `945c87052815b237004d259fe993cc92cbd579b7`

Certified toolbox image:
`sha256:7f4e8f00a1ea130d7b30b8371911239f6bf3df4131533faf04df667668739df7`

## Result

Phase 6 is **PASS**. AIOA now owns a finite, provider-neutral validation and
repair state machine around the existing Phase 2 worker, the real Phase 4
rootless Docker sandbox and the Phase 5 canonical PatchSet policy. Model output
remains candidate data only. It cannot select test commands, assert the actual
changed files, bypass policy, acquire GitHub/AWS authority, or convert an
unknown, timeout or crash into success.

```text
PHASE_4=PASS
PHASE_5=PASS
REAL_CODEX_WORKER_IN_LOOP=PASS
REAL_SANDBOX_IN_LOOP=PASS
MAX_REPAIR_ATTEMPTS=2_ENFORCED
EACH_REPAIR_NEW_PATCHSET_HASH=PASS
REPAIR_EXHAUSTION_CLOSED=PASS
ANTI_TEST_WEAKENING=PASS
FINAL_REVIEW=PASS
FINAL_POLICY_RECHECK=PASS
FINAL_SECRET_SCAN=PASS
FINAL_TESTS_GATES=PASS
SANDBOX_CLEANUP_ORPHANS=0
PRODUCT_GITHUB_WRITES=0
AWS_CALLS=0
PHASE_6_RESULT=PASS
PHASE_7_AUTHORIZED=NO
```

## Closed validation contract

`BoundedRepairLoopCoordinator` implements one initial candidate plus at most
two repair attempts. Every content change is independently derived from the
actual base and candidate workspace, creates a new canonical PatchSet/hash and
must pass this fixed sequence:

- V0 — bounded PatchSet and secret policy before any changed code executes;
- V1 — fixed syntax/static validation;
- V2 — fixed targeted repository test;
- V3 — at most two repair transitions with typed bounded feedback;
- V4 — deterministic anti-cheating and semantic review;
- V5 — fresh secret and complete PatchSet/TOCTOU recheck;
- V6 — fixed final fixture gate.

The Docker validation backend stages the exact already-approved candidate bytes
into a new sandbox rather than letting worker narration or arbitrary command
text choose the executable state. Commands are structured argv owned by AIOA;
the image runs as `65532:65532`, with `network=none`, read-only root, dropped
capabilities, no host home/socket/credential mounts, bounded CPU/memory/PIDs,
bounded output and bounded timeout. Cleanup is mandatory for a PASS.

The deterministic reviewer rejects skip/xfail/disable patterns, removed or
weakened assertions, no-op tests, configuration silencing, fixture-specific
hard-coding, bypass flags, authority/network/credential expansion and
unexpected mocks. A model reviewer is not an authority.

## Required adversarial fixtures

The dedicated Phase 6 unit matrix proves:

- an initially broken implementation reaches `FINAL_PATCH_READY` only after
  the policy and complete V0–V6 ladder pass;
- an insufficient first repair and valid second repair use distinct hashes;
- two failed repairs end as `REPAIR_EXHAUSTED`, never PASS;
- fourth-file expansion and secret introduction are policy denied;
- test skipping, assertion weakening, unrelated edits, hard-coded answers,
  bypass/config/credential/authority expansion are review denied;
- timeout and crash are typed failures and close all opened sessions;
- false changed-file claims never override actual filesystem state;
- same final state re-evaluates to the same canonical PatchSet hash;
- repository text requesting token access or a main push grants no authority.

## Real local mini-E2E

The final authoritative run used the exact implementation commit and immutable
toolbox image above. Its trusted fixture began with a real failing targeted
test (`exit_code=1`, `COMMAND_FAILED`, `network=NONE`). A real Codex App Server
worker edited a disposable candidate workspace without running Python or tests
on the host. AIOA derived the actual one-file `solver.py` PatchSet, ran V0–V6
inside real rootless Docker, reached final PASS and destroyed every owned
sandbox.

The worker reported two changed paths while the authoritative PatchSet found
only `solver.py`. This expected mismatch is preserved as evidence that worker
claims are untrusted and ignored; it did not alter the policy decision.

```text
REAL_E2E_RECEIPT_SHA256=b5668e8e923a0713e795007f0bce30bfe579711668f4b66a050d6672b8014898
FINAL_PATCHSET_SHA256=5787f7a0b81d1f23149a4ad48dd8b341775b7c7c652fbf084c002fcb9425bc4b
LOOP_RECEIPT_SHA256=03a8499a86443dbc34bc5d3702c912862a7bd7f79ce5021cdc91bcfe0da7961b
WORKER_RESULT_SHA256=e69161d73a8a329118a0190287003d5342d3d5081c8459625b4338d1b0b53cdd
WORKER_EVENTS=23
WORKER_HOST_CODE_TEST_COMMANDS=0
CODING_NETWORK=NONE
SANDBOX_CLEANUP_ORPHANS=0
INDEPENDENT_ORPHANS=0
```

An earlier preflight correctly failed on final-tree mode drift: the host umask
materialized trusted fixture files as `0664`, while the sandbox atomic writer
materialized the same content as `0644`. The harness was corrected to normalize
trusted fixture directories to `0700` and regular files to `0644`, reject links
and special files, and verify ownership. A focused regression test binds this
behavior. No policy, image, resource or security control was weakened.

The first B4 invocation after full regression used `/tmp` for its receipt and
was correctly rejected by `B4_OUTPUT_OUTSIDE_PRIVATE_EVIDENCE_ROOT`. B4 was
rerun unchanged with its canonical private `.local/b4` destination and passed.
No rejected invocation is represented as a gate PASS.

## Certification gates

```text
FOCUSED_W1_TO_W6=388/388 PASS
NEW_PHASE_6_TESTS=14/14 PASS
FULL_REGRESSION=1901/1901 PASS, 0 FAIL, 0 SKIP, 725.13s
P0_GATE=15/15 PASS, 136 proof tests
P1_GATE=6/6 PASS, 93 proof tests
CLEAN_CLONE_COMMIT=88d41b1721914f13588319883c85656953b1bf2a
B4_GATE=11/11 PASS, 43 proof tests
B4_RECEIPT_SHA256=ff34a397114c3d70c0df111ddb37f4d5155fb2edec28d53a3aa0c9d6452a5204
RUFF=PASS
PIP_CHECK=PASS
TRACKED_SECRET_SCAN=PASS, 545 files, 0 findings
SECRET_SCAN_RECEIPT_SHA256=2546f33cccf31c9c8237c50281e8a64a41174c9ed4cae265f9711fbed8a1f14b
GIT_DIFF_CHECK=PASS
```

Machine-readable evidence:

- `docs/evidence/w7a/phase6-real-local-e2e.json`
- `docs/evidence/w7a/phase6-loop-certification.json`

Phase 4 and Phase 5 evidence remain unchanged. Frozen W7/B5/B6 history was not
edited or regenerated. No AWS call or mutation, deployment, main push, force
push, tag, PR or product GitHub mutation occurred. A normal builder push of
this W7A branch is the only authorized remote write at checkpoint closure.
Phase 7 remains explicitly unauthorized.

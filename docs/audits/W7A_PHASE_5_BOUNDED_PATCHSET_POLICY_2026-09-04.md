# W7A Phase 5 — Bounded Canonical PatchSet Policy

Date: 2026-09-04 UTC

Work branch: `codex/w7a-agent-execution-slice`

Phase 4 checkpoint: `6626fdf314978b2cbecfbd4ba64105add22dc834`

Phase 5 implementation commit: `f2b2f60003637c03df29d613da62c77877ef9c1e`

Frozen W7/B5/B6 head: `945c87052815b237004d259fe993cc92cbd579b7`

## Result

Phase 5 is **PASS**. AIOA now derives a provider-neutral, bounded PatchSet from
the actual base and final workspace trees. Worker diff text, changed-file lists,
summaries, and narration are not inputs to the decision and grant no authority.
The resulting object is evidence only: mutation, GitHub, and AWS authority are
all fixed to false.

```text
PHASE_4=PASS
CANONICAL_PATCHSET=PASS
DETERMINISTIC_DIFF=PASS
MAX_FILES_CHANGED=3_ENFORCED
MAX_CHANGED_LINES=300_ENFORCED
BINARY=DENY
MASS_DELETE=DENY
TRAVERSAL_LINK_SPECIAL_FILE=DENY
PROTECTED_PATHS=DENY
SECRET_SCAN_HOOK=PASS
TOCTOU_RECHECK=PASS
PROVIDER_NEUTRAL=YES
PRODUCT_GITHUB_WRITES=0
AWS_CALLS=0
PHASE_5_RESULT=PASS
PHASE_6_AUTHORIZED=YES
```

## Actual-state contract

`BoundedPatchSetPolicy` scans two operator-owned, canonical absolute workspace
roots without following links. Every file is read through root-relative
`openat` descriptors with `O_NOFOLLOW`; the device, inode, size, mtime, ctime,
regular-file type, and single-link property are checked before and after the
bounded read. The result is independently reconciled with the existing
`digest_workspace_tree` format used by the Phase 2 worker and Phase 4 sandbox.

The strict `PatchSet` binds:

- UUIDv7 patchset, task, operation, run, trace, worker-run and workspace IDs;
- exact lowercase base HEAD and the existing `RepositorySourceIdentity` tree,
  file count and byte count;
- final tree digest, canonical multi-file unified diff and its SHA-256;
- sorted file operations with exact before/after SHA-256, size and mode;
- file and line totals, binary/deletion/mass-delete facts;
- the deterministic policy version and PASS result;
- a value-free secret-scan summary and self-hashed receipt bound to every
  changed after-content digest;
- provenance and a caller-bound UTC observation time.

The PatchSet itself is self-hashed using the existing canonical workspace JSON
digest. Repeating evaluation over the same context and exact trees produces the
same object, diff, and digest. A subsequent recheck reconstructs the complete
PatchSet from disk; any base or final edit, even one preserving worker narration,
returns typed `PATCHSET_TOCTOU_DRIFT_DETECTED` and cannot reuse the old decision.

## Five-day mutation envelope

The policy permits at most three changed regular UTF-8 files and 300 total
added-plus-deleted lines. It rejects a fourth file before diff construction,
binary/NUL or unsupported encoding, mode changes, `.gitmodules`/submodule
signals, symlinks, multi-link files, special files, traversal, non-NFC paths,
case-fold/Unicode duplicate identities, generated artifacts, and mass deletion
(more than one deleted file or more than 150 deleted lines).

Protected-path rules deny:

- `.git/**`, `.github/**`, remote authority configuration and root Git control
  files;
- `.env*`, credentials, SSH/AWS/cloud/browser/token/key material;
- frozen W7/B5/B6 release/submission evidence and W7A Phase 1–4 audit/evidence;
- dependency/test/lint configuration and the PatchSet/secret-policy-owned files.

Secret-shaped final changed content is rejected before a PatchSet can be
constructed. The denial carries only a stable reason code and `FailureKind`;
the matched value, file bytes, environment, host path, and uncontrolled logs are
not retained or serialized.

## Required adversarial proof

The dedicated Phase 5 suite proves the under-budget source+test happy path,
stable repeat hash, fourth-file denial, 301-line denial, binary denial,
submodule/config and mode-surprise denial, traversal, symlink, hardlink and FIFO
denial, `.git` and frozen-evidence protection, secret rejection without echo,
post-decision TOCTOU invalidation, actual diff dominance over a false model
claim, case ambiguity, generated-artifact denial and mass-delete denial.

```text
FOCUSED_W1_TO_W5=372/372 PASS
NEW_PHASE_5_TESTS=20/20 PASS
FULL_REGRESSION=1887/1887 PASS, 0 FAIL, 0 SKIP, 714.10s
P0_GATE=15/15 PASS, 136 proof tests
P1_GATE=6/6 PASS, 93 proof tests, clean clone included
CLEAN_CLONE_COMMIT=f2b2f60003637c03df29d613da62c77877ef9c1e
B4_GATE=11/11 PASS, 43 proof tests
B4_RECEIPT_SHA256=ec1504981ed79d9b26b6b0d23e5b5dfd71d37e8585a4c906cf6fdc14b857f559
RUFF=PASS
PIP_CHECK=PASS
TRACKED_SECRET_SCAN=PASS
GIT_DIFF_CHECK=PASS
```

The first P1 run occurred before the implementation commit and correctly
returned P1-06 `SOURCE_WORKTREE_NOT_CLEAN`. No PASS was claimed. After the
implementation was committed and the temporary local `.venv` symlink was
removed, the direct clean-clone proof and complete P1 gate both passed against
the exact commit above.

The self-hashed receipt is
`docs/evidence/w7a/phase5-patchset-certification.json`. Phase 4 remains frozen
and unchanged. No AWS call or mutation, deployment, main push, force push, tag,
PR, or product GitHub mutation occurred. Phase 6 is authorized; Phase 7 remains
explicitly unauthorized.

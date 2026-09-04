# W7 final release-candidate — controlled B5 recertification

## Result

```text
W7_GATE=PASS
B5_BUILD_COMPLETE=PASS
B6_PUBLICATION_READY=PASS_LOCAL_ONLY
AWS_CALLS=0
DEPLOYMENTS=0
REMOTE_PUSHES=0
PUBLICATION_ACTIONS=0
W8_AUTHORIZED=NO
```

The W7 gate recovered through the canonical fail-closed path. Nothing was deployed, uploaded,
published, pushed to a remote, or sent to AWS.

## Root cause and decision

The historical B5 certificate was bound to source commit
`797c94e72151c46504b9ae81412738aa6b253e8a`. W7 intentionally added the exact W4 and W7 helper
closure to the default-deny Docker build context. Commits `7c8a8fd` and `758cff2` changed
`.dockerignore`, while the Dockerfile copied those same reviewed helpers. Consequently, the current
source artifact and Docker context no longer matched the historical B5 identities. The three
`B5_SOURCE_ARTIFACT_DRIFT` failures were correct.

Git history, the W7 packaging tests, and the matching Dockerfile changes prove that the drift was
intentional. The change was therefore recertified; it was not reverted, hidden from membership,
or accepted by weakening a detector.

## Controlled two-stage B5 transition

Stage A commit `5573875aa0f708aa7610605930fda04392bc0aeb` introduced an explicit
`RECERTIFICATION_IN_PROGRESS` control state for candidate source
`bd2103da727fdb3a7fd846d6f9084c36980c01b7`. The canonical validator rejected release readiness
in that state. Historical BUILD_COMPLETE evidence remained historical and could not satisfy the
new candidate gate.

The first full regression then passed 1,739/1,739 in 791.89 seconds. Only afterward, Stage B commit
`794845e9f08d8057eda7506a924fb24af56885e9` atomically bound all canonical B5 evidence to:

```text
SOURCE_COMMIT=bd2103da727fdb3a7fd846d6f9084c36980c01b7
SOURCE_TREE_GIT_OID=b298f8c12c92c986a5c2cebc1c7216dd8be350c8
SOURCE_ARTIFACT_SHA256=6e671cf9943b70802a7f1330256050c453193b5c91ffbfc99063e2e3974afe37
IMAGE_ID=268cfce43a682ea364eb7bc01bdb2f1ae9dc8f8c0bf2da71c2fdd2a8c4be54c1
IMAGE_DIGEST=sha256:f5f5647cfc0deb5361a8d538e55cf7c3a3ede9b07c96f50e8b9ebfb19c581c4d
IMAGE_REFERENCE=localhost/aioa-portable:w7-rc-bd2103da727f
```

No `PENDING` field is accepted as release evidence. `RECERTIFICATION_IN_PROGRESS` cannot validate
as BUILD_COMPLETE. A stale pytest assertion cannot coexist with a new source/image identity.

## Regression and release gates

| Gate | Result |
| --- | --- |
| Full pytest before BUILD_COMPLETE | PASS — 1,739/1,739, 791.89 s |
| Full pytest after BUILD_COMPLETE | PASS — 1,739/1,739, 781.45 s |
| Final full pytest after B6 packaging changes | PASS — 1,739/1,739, 774.25 s |
| P0 | PASS — 15/15 gates, 136 proof tests, 0 skipped |
| P1 | PASS — 6/6 gates, 93 proof tests, 0 skipped, clean clone included |
| B4 | PASS — 11/11 scenarios, 43 proof tests |
| Canonical B5 validator | PASS — BUILD_COMPLETE, four evidence artifacts |
| Reviewer manifest | PASS — 28 claims, zero live receipts |
| Ruff | PASS |
| pip check | PASS |
| Source secret scan | PASS — 492 files, zero findings |
| git diff --check | PASS |

The final JUnit receipt is SHA-256
`14a583b1d89cbe7123121135a6df478b45270bde4656234d4e73e7712a7c63ca`.

## B6 local publication readiness

The B6 exporter now derives the public B5 image reference from the certified artifact manifest and
fails closed on source/image disagreement. Internal `docs/evidence/workspace/` receipts are excluded
from the public candidate instead of weakening the privacy scanner.

Two initial exports and two certification-bearing final exports were byte-identical within their
respective pairs. A Git-free clean room verified 392 internal candidate checksums, two identical
offline wheels, source import, and the fixed Render startup profile. That profile proved missing
token fail-closed behavior, token mode 0600, removal of `AIOA_OPERATOR_TOKEN` from the child,
canonical child argv, `/health`, `/ready`, zero external egress, and zero AWS calls.

The final public scan passed 393 files with zero findings. The local-only archive is:

```text
PATH=dist/submission/w7-b6-2026-09-04/aioa-agents-for-humans-publication-candidate.zip
SHA256=0030de3e37dcd073b35b2112c86e1ba0f7508b42c4653916a10c90b86b9cd713
UPLOADED=NO
```

The runtime container remains the exact B5 clean-clone-certified image. B6 did not build or claim a
second publication-only OCI image, and no public endpoint claim is made.

## Evidence

- `docs/evidence/release/w7-b5-recertification-state.json`
- `docs/evidence/release/w7-release-manifest.json`
- `docs/evidence/release/w7-container-hero.json`
- `docs/evidence/submission/w7-b6-reproducibility.json`
- `docs/evidence/submission/w7-b6-final-public-scan.json`
- `docs/evidence/submission/w7-publication-bundle.json`

W8 is explicitly not authorized by this checkpoint.

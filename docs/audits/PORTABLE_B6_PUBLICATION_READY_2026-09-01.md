# Portable B6 publication-ready audit — CMD recertified 2026-09-02

## Result

```text
PHASE=B6_PUBLICATION_READY_LOCAL_CMD_RECERTIFICATION
PUBLICATION_READY=PASS
PUBLIC_SOURCE_COMMIT=46ce221e81f88d82df75d67e144d9a2231c54d64
B6_REPRODUCIBILITY_COMMIT=986c5b2d174e9e745338b141e3f37b1c28ca2997
LICENSE=MIT_CONFIRMED_FROM_INITIAL_COMMIT
AWS_CALLS=0
AWS_MUTATIONS=0
EXTERNAL_DEPLOYMENTS=0
REMOTE_PUSHES=0
PUBLICATION_ACTIONS=0
PUBLIC_BUNDLE_UPLOADED=NO
```

B6 produced and certified a local, sanitized hackathon candidate. It did not publish a repository,
push a branch or image, upload an archive, create an endpoint, deploy infrastructure, contact AWS,
record a video, send an email, or submit a Devpost entry.

## Sanitized source

The deterministic builder read only Git blobs from exact source commit
`46ce221e81f88d82df75d67e144d9a2231c54d64`. It classified all 420 tracked files:

| Classification | Count | Export behavior |
| --- | ---: | --- |
| `PUBLIC_REQUIRED` | 178 | included |
| `PUBLIC_ALLOWED` | 152 | included |
| `LEGAL_REVIEW` | 2 | included after MIT/prior-art review |
| `PRIVATE_INTERNAL` | 87 | excluded |
| `GENERATED` | 1 | root README replaced by reviewed public overlay |
| `SECRET_RISK` | 0 | none present |

The first candidate scan correctly stopped on `operator@example.test` inside a URL-policy unit test.
The scanner was not weakened: source commit `46ce221…` adds only the IANA-reserved `.test` suffix to
the existing test-directory synthetic-email classification and adds focused coverage. Real-domain
email values and the same reserved value outside `tests/` still fail closed. Both initial exports
were rebuilt from the new exact commit before any certification evidence was accepted.

The exported README is the reviewed B6 overlay. The resulting B6 image is therefore not claimed
byte-identical to B5 even though runtime source, Dockerfile, locks, and safety behavior are unchanged.

## Deterministic clean-room reproduction

Two initial exports were byte-identical. The selected archive was unpacked into a separate directory
with no `.git`, private audits, deployment evidence, or submission evidence. Only the candidate
README and reproducibility guide were used.

```text
INITIAL_ARCHIVE_SHA256=070709bcf07168fad533d248cce89587ab14a3ed4605990bbe906c838f1043cb
INITIAL_MANIFEST_FILE_SHA256=2cc3bdf547a846baa591b21c7fa48edc71f096ba705c77620cd3282d00aeb776
INITIAL_PAYLOAD_TREE_SHA256=1c9048d7ffd09e58fec551ba089e661edc04605160339d588d4a8a4769ade723
CANDIDATE_SHA256SUMS=PASS 336/336
SANITIZED_CLEAN_ROOM_BUILD=PASS NO_CACHE
HASH_PINNED_DEPENDENCIES=PASS
PIP_CHECK_IN_CONTAINER=PASS
DEFAULT_CMD_START=PASS
HEALTH=PASS HTTP_200
READINESS=PASS HTTP_200
SANITIZED_APPROVE=PASS
SANITIZED_DENY=PASS
SANITIZED_RECOVERY=PASS
SANITIZED_REPLAY=PASS
CLAIMS_PROOF_AUDIT=PASS 29/29
```

Two isolated, network-disabled judge invocations emitted identical bytes and inner receipt SHA-256
`f365b07702e43c3848b3470453910b2239d640e8e9ec22a917790a702c110ba3`; the complete JSON file
SHA-256 was `f829b18ff509c40288b134579c0c01a650628780a9ccc15f016b14a47346bb73`.
Each proved one approved mock mutation only after decision, denial with zero mutation, restart
recovery/reconciliation, replay and binding rejection with zero mutation delta, five fail-closed
probes, zero external connections, zero provider calls, zero AWS calls, and zero AWS mutations.

## Container identity and host limitation

```text
LOCAL_REFERENCE=localhost/aioa-portable:b6-public-cmd-46ce221e81f8
RUNTIME_IMAGE_ID=a5627d4a90a4d5aeb596f1028b2f1923d6bd23e407f02c042ef3c70365cdfda7
BUILD_MANIFEST_DIGEST=sha256:d3a1e9994487af1067ab5b296deef9a727eb9a21073cabeff6c131e0d03fbc0d
LOCAL_MANIFEST_DIGEST=sha256:e810c00a2f79bd4404e19a28096c4fae53154594a46d9e6224f71e2a33543e70
OCI_ARCHIVE_SHA256=c15d896412d14d0fce5ac5f42ede06ec3af866fdc8e1e4ae5ca83f7a3acfbe36
IMAGE_SIZE_BYTES=219807733
CONFIGURED_USER=aioa
CONFIGURED_ENTRYPOINT=NONE
DEFAULT_CMD=python -m aioa_cloudops_agent.portable_server
NETWORK=none
ROOT_FILESYSTEM=read-only
CAP_EFF=0000000000000000
NO_NEW_PRIVS=1
TOKEN_MODE=0600
```

The image was first run with no command or Entrypoint override; the default CMD emitted `READY` and
stopped cleanly on `SIGTERM`. Because this constrained rootless host cannot `exec` into the child
mount namespace, the endpoint proof used a single in-container supervisor under network `none` to
launch the exact same `python -m aioa_cloudops_agent.portable_server` argv, probe `/health` and
`/ready`, verify token mode `0600`, and stop it cleanly. This combines a real default-CMD start proof
with endpoint evidence; it does not replace the image configuration assertion.

The host has no usable subordinate-ID mapping for image UID/GID 65532. B6 process invocations used
the disclosed local `0:0` compatibility override and are not represented as a B6 non-root proof.
Non-root authority remains the fresh, source/image/digest-bound B5 exact-root-filesystem receipt,
which proves UID/GID 65532, zero capabilities, `NoNewPrivs=1`, health/readiness, server PID 1, and
token mode `0600`. The operator-local mount-namespace wrapper changes neither image nor host path and
is not a deployment configuration.

## Privacy and claims audit

The final candidate, including its B6 report, contains 338 regular files. The final scan read 335
text files and reviewed three expected image assets. It found no secret, private key, credential
file, personal PDF, real email, phone number, local user path, browser/session file, or AWS account
identifier. Fourteen synthetic test fixtures were classified without emitting matched values.

```text
PUBLIC_SECRET_SCAN=PASS
PUBLIC_PRIVATE_DATA_SCAN=PASS
FINDINGS=0
SCAN_FILE_SHA256=e93d3d1083df923020ab1a915d0c24157e33c57a7584c95103ad3a59b11718ce
SCAN_RECEIPT_SHA256=ea92b8840474de8fa44e472df990e1506cd6f29b4fd8829460277fbd4a9b7534
CLAIMS_PROOF_AUDIT=PASS 29/29
UNSUPPORTED_CLAIMS=0
```

The claims matrix forbids promotion to live AWS, live Bedrock, production readiness, public
availability, real cloud mutation, registry publication, or final submission. The MIT license and
prior-art disclosure originate in initial commit
`d813290727b89017bd348c04f68a7f07156652f7`; no human license decision remains open.

## Frozen local bundle

Two final exports built from unchanged B6 source commit `46ce221…` and injected the committed
reproducibility report byte-for-byte. Their complete candidate trees and archives were identical.

```text
PUBLIC_BUNDLE=dist/submission/portable-b6-2026-09-02/aioa-agents-for-humans-publication-candidate.zip
ARCHIVE_BYTES=4473912
ARCHIVE_SHA256=297136b4d166661608e0e9c0a332b428ffdefe187f6810b177d57b68ae63610a
MANIFEST_FILE_SHA256=2b48008e30f805174551171959d71096d6ee480631fc44be83bc9083670a82b3
PAYLOAD_TREE_SHA256=a8d9c3ba89edb06ba503135c8e2f017f17ac46f7010886a0b8239b02f61ffdfe
B6_REPORT_SHA256=39aba73cb8633ac9b84a8f70f7b44f4acc95aacf33e132e3b362db9811470398
DETERMINISTIC_REBUILDS=2/2 IDENTICAL
ARCHIVE_UPLOADED=NO
```

The archive contains the sanitized source, `PUBLICATION_MANIFEST.json`,
`PUBLICATION_EXCLUSIONS.md`, `SHA256SUMS`, `B5_BUILD_COMPLETE_REFERENCE.json`, and
`B6_REPRODUCIBILITY_REPORT.json`. The committed local-bundle authority is
`docs/evidence/submission/portable-b6-publication-bundle.json`.

## Final B6 gate

```text
SANITIZED_CLEAN_ROOM_BUILD=PASS
SANITIZED_DEFAULT_CMD_START=PASS
SANITIZED_HEALTH_READINESS=PASS
SANITIZED_APPROVE=PASS
SANITIZED_DENY=PASS
SANITIZED_RECOVERY=PASS
SANITIZED_REPLAY=PASS
CLAIMS_PROOF_AUDIT=PASS
PUBLIC_SECRET_SCAN=PASS
PUBLIC_PRIVATE_DATA_SCAN=PASS
PUBLIC_BUNDLE_CREATED=YES
PUBLIC_BUNDLE_UPLOADED=NO
REMOTE_PUSHES=0
PUBLICATION_ACTIONS=0
EXTERNAL_DEPLOYMENTS=0
PUBLICATION_READY=PASS
HARD_BLOCKER=NONE
```

B6 stops at local publication readiness. Deployment, registry push, upload, repository visibility
change, video publication, and submission require a later explicit human-authorized phase.

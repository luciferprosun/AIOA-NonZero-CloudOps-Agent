# Portable B6 publication-ready audit — Render startup recertification 2026-09-02

## Result

```text
PHASE=B6_PUBLICATION_READY_LOCAL_RENDER_START_RECERTIFICATION
PUBLICATION_READY=PASS
PUBLIC_SOURCE_COMMIT=a7bb1d6eb7ff5a86126f02af6758f0298289816b
B6_REPRODUCIBILITY_COMMIT=b69fbfda9cb5d0244f55938755312ac820bf0e0e
LICENSE=MIT_CONFIRMED_FROM_INITIAL_COMMIT
AWS_CALLS=0
AWS_MUTATIONS=0
EXTERNAL_DEPLOYMENTS=0
REMOTE_PUSHES=0
PUBLICATION_ACTIONS=0
PUBLIC_BUNDLE_UPLOADED=NO
```

B6 produced and certified a local, sanitized candidate after the Render startup-script change. It
did not publish a repository, push an image, upload an archive, create a service or endpoint,
contact AWS, send email, record video, or submit an external entry.

## Sanitized source and deterministic export

The builder read only Git blobs from exact source commit
`a7bb1d6eb7ff5a86126f02af6758f0298289816b`. It classified all 421 tracked files:

| Classification | Count | Export behavior |
| --- | ---: | --- |
| `PUBLIC_REQUIRED` | 179 | included |
| `PUBLIC_ALLOWED` | 152 | included |
| `LEGAL_REVIEW` | 2 | included after MIT/prior-art review |
| `PRIVATE_INTERNAL` | 87 | excluded |
| `GENERATED` | 1 | root README replaced by reviewed public overlay |
| `SECRET_RISK` | 0 | none present |

Two initial exports were byte-identical. The selected archive was unpacked into a separate
directory with no `.git`, private audits, deployment evidence, or submission evidence. The exported
`scripts/render_start.sh` retained source mode `0755`.

```text
INITIAL_ARCHIVE_SHA256=3dafc6b9a3be452e2c42c3314197f6f317c7d84493a835418a906ef91d6a7548
INITIAL_MANIFEST_FILE_SHA256=5dd24bee76f5142737d251dcca604165250a62eec8dacccd09403c3579133d09
INITIAL_PAYLOAD_TREE_SHA256=8a9101f1be989b09dffa9fcb479bf95a92da9bf7f0b9149f41e36b0b082b112f
CANDIDATE_SHA256SUMS=PASS 337/337
INITIAL_PUBLIC_SCAN=PASS 338 regular files 0 findings
```

## Clean-room container and Render startup proof

The clean-room image was built without cache from the sanitized candidate with hash-pinned
dependencies. `pip check` passed. The image kept no configured Entrypoint and retained the canonical
default CMD, while the fixed Render command invoked one installed executable:

```text
LOCAL_REFERENCE=localhost/aioa-portable:b6-public-render-a7bb1d6eb7ff
IMAGE_ID=a310690a3d411ea133ba2e6aedb05fc9a4279ee7f0a8f16c4ddc198b3d945833
MANIFEST_DIGEST=sha256:6602875706bfdbd68444ac83c928d758781aaac8ab9b4358e87d3f7e3f49f9d5
OCI_ARCHIVE_SHA256=4eac968a43a84908fac42e7d26da48a8ccd6b780cc06035f958f678896abd534
IMAGE_SIZE_BYTES=219815045
CONFIGURED_USER=aioa
CONFIGURED_ENTRYPOINT=NONE
DEFAULT_CMD=python -m aioa_cloudops_agent.portable_server
RENDER_COMMAND=/usr/local/bin/aioa-render-start
INSTALLED_SCRIPT_MODE=0555
```

The default CMD process remained running until an exact controlled local stop. A separate
network-disabled image proof invoked `/usr/local/bin/aioa-render-start` and established all of the
following without printing the synthetic token:

```text
RENDER_START_SCRIPT=PASS
MISSING_TOKEN_FAIL_CLOSED=PASS EXIT_2
TOKEN_MODE=0600
AIOA_OPERATOR_TOKEN_IN_CHILD_ENV=ABSENT
CHILD_ARGV=python -m aioa_cloudops_agent.portable_server
HEALTH=PASS HTTP_200
READY=PASS HTTP_200
AWS_AUTHORITY=false
EXTERNAL_NETWORK_AUTHORITY=false
REAL_CLOUD_MUTATIONS=false
```

The exact exported root filesystem also passed a Bubblewrap 0.9.0 non-root proof. The startup
script ran as inner UID/GID 65532, then `exec` replaced it with the canonical server as PID 1. The
proof measured zero effective capabilities, `NoNewPrivs=1`, token ownership 65532:65532 and mode
`0600`, health/readiness, and absence of `AIOA_OPERATOR_TOKEN` from the server environment. The
Bubblewrap process exited cleanly after `SIGTERM`.

The local Podman host lacks a usable subordinate-ID mapping for image UID/GID 65532. Only after the
exact image-ID/digest/source-bound non-root proof, the two network-disabled judge flows used the
gate's narrow `0:0` compatibility override. That local accommodation is not a deployment setting.

The image-root privacy scan read 11,288 regular files and 284 application files, found zero secrets,
credentials, private keys, Git metadata, or baked operator tokens, and recorded zero AWS calls and
zero external connections.

## Judge flow and claims proof

Two isolated judge invocations produced identical inner portable receipt SHA-256
`f365b07702e43c3848b3470453910b2239d640e8e9ec22a917790a702c110ba3`.
The image/source-bound aggregate gate receipt SHA-256 was
`d6372f42bab782dbbb44558b54e87f3de0eaac52486b85ca0c148a4a864e74b2`.

Each invocation proved one approved mock mutation only after the human decision, denial with zero
mutation, restart recovery/reconciliation, replay rejection, binding-tamper rejection, five
fail-closed probes, zero external connections, zero provider calls, zero AWS calls, and zero AWS
mutations. Reviewer-evidence validation passed 28 claims with zero live receipts; the claims
referenced 31 unique proof paths.

## Final privacy gate and frozen local bundle

Two final exports rebuilt from the unchanged B6 source commit and injected the committed B6
reproducibility report byte-for-byte. Their complete candidate trees and ZIP archives were
identical. The final scan reviewed 339 regular files: 336 text files and three expected image
assets. It found no secrets or private data and emitted no matched values.

```text
PUBLIC_BUNDLE=dist/submission/portable-b6-2026-09-02-render-start/aioa-agents-for-humans-publication-candidate.zip
ARCHIVE_BYTES=4480704
ARCHIVE_SHA256=af07a6a4c085db60ebd66971bbe5ed42fb3aa7de5d6b7486ffc70b59943bf45a
MANIFEST_FILE_SHA256=4fea85a4fa74362a78ecc937d05c2dcc0ff185bf1b05074105644768fd22ba24
PAYLOAD_TREE_SHA256=f6d6595cf381371525b8f46d0fab06362a4be482059501dd10b0d4c2ef4840cc
B6_REPORT_SHA256=49c4923bc3fd02da7f0bb0a37d0448a68a29d9e678738ec3d7c96fbf8b008f3e
FINAL_SCAN_FILE_SHA256=fbcb50e77d29eb7c973660cd57d7d83998f392bdaa0473ebd42aa3bafbb843fb
FINAL_SCAN_RECEIPT_SHA256=8e2791cb66113e12724c42080d3b24356ec8179b17439d414a47be1188b7de13
DETERMINISTIC_REBUILDS=2/2 IDENTICAL
PUBLIC_SECRET_SCAN=PASS
PUBLIC_PRIVATE_DATA_SCAN=PASS
FINDINGS=0
ARCHIVE_UPLOADED=NO
```

## Final B6 gate

```text
SANITIZED_CLEAN_ROOM_BUILD=PASS
SANITIZED_DEFAULT_CMD_START=PASS
RENDER_START_SCRIPT_BOOTSTRAP=PASS
SANITIZED_NONROOT_PID1=PASS
SANITIZED_HEALTH_READINESS=PASS
SANITIZED_APPROVE=PASS
SANITIZED_DENY=PASS
SANITIZED_RECOVERY=PASS
SANITIZED_REPLAY=PASS
IMAGE_PRIVACY_SCAN=PASS
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

B6 stops at local publication readiness. Render deployment, registry push, upload, repository
visibility changes, video publication, and submission remain separate human-authorized phases.

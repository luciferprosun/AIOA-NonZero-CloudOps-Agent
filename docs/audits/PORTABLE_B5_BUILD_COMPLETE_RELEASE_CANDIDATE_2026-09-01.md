# Portable B5 build-complete release candidate

## Result

```text
BUILD_COMPLETE=PASS
PHASE=B5_BUILD_COMPLETE_CMD_RECERTIFICATION
FROZEN_SOURCE_COMMIT=c262c9f25bbe069f17a05da7221dbce606edb7b8
FROZEN_SOURCE_TREE=def4ccbb9bb07f6843f8efb2e48c86c1741e8ac3
EVIDENCE_FREEZE_COMMIT=dc09bfb0e8d9d265fe592882713d3c156bcd01ff
APPLICATION_VERSION=0.2.0rc1
PLATFORM=linux/amd64
PYTHON_VERSION=3.12.14
AWS_CALLS=0
AWS_MUTATIONS=0
DEPLOYMENTS=0
IMAGE_PUSHES=0
REMOTE_GIT_PUSHES=0
PUBLICATIONS=0
```

B5 freezes one local, provider-neutral OCI artifact built from a detached clean clone. It does not
deploy that artifact, publish it to a registry, create a public endpoint, contact AWS, or promote an
offline/mock receipt to live-cloud evidence.

## Frozen image

```text
LOCAL_REFERENCE=localhost/aioa-portable:b5-cmd-c262c9f25bbe
IMAGE_ID=d5eca6b273309ba0fda6e143af47ea0c9c160a7605b29dd6f1fa8262c8d720e9
LOCAL_OCI_MANIFEST_DIGEST=sha256:371b7c5b3bc9d88fe07aba54a5bd4b3e69a526ea1ff313b09253b75983e5856a
IMAGE_SIZE_BYTES=219807918
REGISTRY_DIGEST=NONE_NOT_PUSHED
CONFIGURED_USER=aioa
EFFECTIVE_CERTIFIED_UID_GID=65532:65532
CONFIGURED_ENTRYPOINT=NONE
DEFAULT_CMD=python -m aioa_cloudops_agent.portable_server
BASE_IMAGE=docker.io/library/python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254
```

The tag is a mutable local convenience. The recorded manifest digest, image ID, and exact source
label form the frozen local identity. No registry digest exists because no push occurred.

The local Podman 4.9.3 host has only one usable host UID/GID mapping, so its default-user probe could
not map image UID/GID 65532 and was not counted as passing. A private Bubblewrap user namespace ran
the exact exported image root filesystem and proved UID/GID 65532, zero effective capabilities,
`NoNewPrivs=1`, server PID 1, health/readiness, and token mode `0600`. Only after that bound proof did
the two judge flows use the narrowly allowed local `0:0` compatibility override. The local Podman
wrapper merely works around an inaccessible parent path in a private mount namespace; it does not
change the host, image, flow mounts, privileges, or deployment configuration. The gate's
`BOUND_EXTERNAL_OCI_RUNTIME` value is a schema label for this external proof path, not a claim that
the failed nested-crun attempt succeeded.

## Deterministic build inputs

| Input | SHA-256 |
| --- | --- |
| `Dockerfile` | `2c406cf165e9e21c74f85a6ae3123ee1498790c15f3586cd8ffe548309dd8a7e` |
| `.dockerignore` | `c6bf8a28a6fbcb1ba2e94fcdedcb00cf6f6620556262c88629dd14d800346458` |
| `requirements/build.lock` | `d46492123b794c100b45c485f2981c1a12f71388f61439a5a662d850b19039a5` |
| `requirements/portable.lock` | `a7be92862cb66b67f2bf5b664f62abee1dbd48d65e2ee12fbcbaa5be2dff5dcd` |
| project wheel | `fe5b5df0448bf41c9aa0d6460b998adf280cab567b9ba688e5111cb71c0ff395` |
| portable runtime contract | `c5af5e77349a1038d860f3108a2bbaee6fbb6d3df7340f931095551a72240233` |
| container judge runbook | `2c1e96fdade714f2e63738dfbe61b5230512a43955d36ac125f8205eed78e663` |
| submission demo runbook | `3ee0e75aab70b9e63860e7deb3e5785cfd6a1df9ac60ea9462d9022fe61d3f47` |

The image build produced the pinned project wheel and a runtime closure of 55 hash-pinned
dependencies plus the project wheel and base-image `pip`: 57 installed distributions. The checked-in
package manifest records installed name, version, provenance, and available artifact hash.

## Container execution evidence

The exact source-bound image passed two separate `run --rm` invocations with network `none`, a
read-only root filesystem, a hardened `/tmp` tmpfs, all capabilities dropped, no new privileges,
zero published ports, zero shared mounts/state, and no inherited credential environment. Both
invocations emitted the deterministic portable receipt SHA-256
`f365b07702e43c3848b3470453910b2239d640e8e9ec22a917790a702c110ba3` and proved approve, deny,
restart recovery/reconciliation, replay rejection, and binding-tamper rejection. Mutations were zero
before approval; approve performed exactly one mock mutation, while deny/recovery/replay/tamper
deltas remained zero. Provider network, external network, AWS calls, and AWS mutations were zero.

## Image privacy scan

The exact exported root-filesystem scan covered 11,287 regular files and 209,599,215 bytes,
including 284 application-package files. It found no Git metadata, environment file, AWS credential
file/value, private-key block/file, or baked operator token. Result: `PASS`, findings: `0`.

## Release evidence

| Evidence | File SHA-256 | Internal SHA-256 |
| --- | --- | --- |
| package manifest | `e9d182b2cd503fcc6e805af96d532dd14ab67765c5a6021e8dc4762990e0f36d` | `bc92cfd42df2c533c513725bf4ba7ec8005ebb77cf488b9dd32a70750a408e42` |
| artifact manifest | `765f917d8a1eee038d3f4deefdc858cd7785838b0f5039091584950ec396f442` | `e9a5c558e0a8f01fc69a215297cb689f71860812c42838a8746ce1eb786d99fd` |
| container gate | `2672ab2285dfdfc7e274aa4129f32333b259038781a22f1ffbadae44e1287d67` | `f9f5861882cba8060ef05fd8f189848b07488dba24912af4f6624d947a503402` |
| image privacy scan | `909d99235c5eb66d2e471ddf7cccec7cd7bb26b8123fff04ede95cd56a11049c` | `b418eeba1f393cf7d020061b648cb0812aeeef95f531cf522fef3bf380bcee62` |
| non-root runtime | `22f8447678f89f255ab0c72a6b941f5189a4b420610387891a9be134b4270601` | image/digest/source bound |
| `portable-b5-SHA256SUMS` | `8f4927a87f0adb2aa2beb737faa483adb64cbaa3f8ceea2b494d1de685a136df` | deterministic sorted list |
| build-complete attestation | `9e256e6a8f5b1229010bd0c040b196dd6ab6621d0294cccdaf53f5323c73f652` | `5106f99fb3ebfe38d1fde9895b85782ee89a686c2e2fd30db5ba2da62de16e43` |

The generator re-reads every bound source file from frozen Git commit `c262c9f…`, rejects blob
drift, and independently recomputes receipt, manifest, attestation, file, and checksum hashes.

## Final B5 gate

```text
FULL_PYTEST=PASS 1465 passed 0 failed 0 skipped
P0=PASS 15/15 136 proof tests
P1=PASS 6/6 93 proof cases
B4=PASS 11/11 43 proof tests
CLEAN_CLONE=PASS 6/6
RUFF=PASS
PACKAGE_BUILD=PASS
PIP_CHECK=PASS
SECRET_SCAN=PASS 0 findings
EVIDENCE_VALIDATOR=PASS 28 claims 0 live receipts
NATIVE_PORTABLE_FLOW=PASS
CONTAINER_JUDGE_GATE=PASS 2/2
NONROOT_EXACT_ROOTFS_PROOF=PASS
IMAGE_EXPORT_PRIVACY_SCAN=PASS 0 findings
DIFF_CHECK=PASS
```

The first full-suite diagnostic encountered one transient local-tool availability result; the exact
pinned AWS CLI was present, the isolated test passed, and a quiesced complete rerun passed all 1,465
tests. No test or gate was weakened.

## Freeze rule

Any runtime source, dependency lock, Dockerfile, build-context policy, package-data manifest,
portable runtime contract, container runbook, submission demo runbook, or bound evidence change
invalidates `BUILD_COMPLETE`. It requires a new clean-clone image build, all gates, and a new local
artifact identity before deployment or publication can be considered.

# Portable B5 build-complete release candidate

## Result

```text
BUILD_COMPLETE=PASS
PHASE=B5_BUILD_COMPLETE_RENDER_START_SCRIPT_RECERTIFICATION
FROZEN_SOURCE_COMMIT=797c94e72151c46504b9ae81412738aa6b253e8a
FROZEN_SOURCE_TREE=bd9997296560aa9e57d5fa38001a40a7c38f6a38
EVIDENCE_FREEZE_COMMIT=PENDING_CURRENT_RECERTIFICATION_COMMIT
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
LOCAL_REFERENCE=localhost/aioa-portable:b5-render-797c94e72151
IMAGE_ID=2f4b9a0d2708ae82aeda558e45271b59b192894a3b09a1831723ad42e8fe78b4
LOCAL_OCI_MANIFEST_DIGEST=sha256:bdf35995e5588ccb93348f0784411d32d0aeb480483b1f34d530c4e3f34edbc3
IMAGE_SIZE_BYTES=219814532
REGISTRY_DIGEST=NONE_NOT_PUSHED
CONFIGURED_USER=aioa
EFFECTIVE_CERTIFIED_UID_GID=65532:65532
CONFIGURED_ENTRYPOINT=NONE
DEFAULT_CMD=python -m aioa_cloudops_agent.portable_server
RENDER_START_SCRIPT=/usr/local/bin/aioa-render-start
RENDER_START_SCRIPT_MODE=0555
RENDER_DOCKER_COMMAND=/usr/local/bin/aioa-render-start
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
| `Dockerfile` | `4640463904ced78776f5f482510e9f117d7ee2e0b6a8e04c5ba83e349378bc8f` |
| `.dockerignore` | `0e6b8400e2813f0be52a5f3f5243d520cbbe740b286a44749e8e6db368265812` |
| `scripts/render_start.sh` | `d350917c132a338605f630fde97a2ac017e1664fe9cf413a7153827326e6d250` |
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

The exact exported root-filesystem scan covered 11,288 regular files and 209,599,663 bytes,
including 284 application-package files. It found no Git metadata, environment file, AWS credential
file/value, private-key block/file, or baked operator token. Result: `PASS`, findings: `0`.

## Release evidence

| Evidence | File SHA-256 | Internal SHA-256 |
| --- | --- | --- |
| package manifest | `9805a68b2435625cd7bdc7263056d71fbc550cb6d943d808c94a55f3a3ef0479` | `b1f5e23fb592a3b79cd7e3ef36cb991c31d0d1d9c5d19b35705c55ea45cb2b12` |
| artifact manifest | `98846b9723e1921ca2b60b8f47a90f3bb7a04c5de9d529a2359e115ff177e8c3` | `5c810c3abe1ccd77317de7282b472694ed3e2304b4d5306bd18fdc022effe241` |
| container gate | `1b0bef9f4cd43331bf72bdd418ad1bc8e61f2220a097823fa78066da000e13c6` | `1b75a75026625a1549d52d855097873e0b6fb969a66c3e75e8ad51351c291aee` |
| image privacy scan | `8a8b9a56b351d5c637dc03d4630109048a2307f1a4122e4387ee157b5775385a` | `4a1fd5356a1622916ba195c3084d810ec0d9b878a19ef9096fe93a4b23fe8b06` |
| non-root runtime | `30cc83d71de47e0a3e79ceaa2a268900ed5019a930104c7276556ab91afb8876` | image/digest/source bound |
| `portable-b5-SHA256SUMS` | `042ac6cc58d8cc2cc0ac92b25cd9d2cafbce0660c960ab3a77d7c3de7e1fe4dd` | deterministic sorted list |
| build-complete attestation | `66f9df7c5314b5e1606d5e3a103b352bd8d38ac8751b7a36ba89b3aefa646810` | `5e2c929f9ede0ac16193c4cbef847d1a96fc8207f5dcac009c5dcbf5fdcdaaa7` |

The generator re-reads every bound source file from frozen Git commit `797c94e…`, rejects blob
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

This recertification's complete full-suite run passed all 1,465 tests on its first run. P1's
clean-worktree command proof was run after the generated evidence was safely stashed and passed
without changing code or weakening any gate.

## Freeze rule

Any runtime source, dependency lock, Dockerfile, build-context policy, package-data manifest,
portable runtime contract, container runbook, submission demo runbook, or bound evidence change
invalidates `BUILD_COMPLETE`. It requires a new clean-clone image build, all gates, and a new local
artifact identity before deployment or publication can be considered.

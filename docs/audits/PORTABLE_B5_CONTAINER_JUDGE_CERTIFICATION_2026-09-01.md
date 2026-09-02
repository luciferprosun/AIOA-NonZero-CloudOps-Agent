# Portable B5 container judge certification

Date: 2026-09-02 CMD recertification

Phase: B5, clean-clone container judge flows

CMD implementation commit: `5d10229d9ca0d243068c0ee77a0c90a4e722689c`

Frozen image-source commit: `c262c9f25bbe069f17a05da7221dbce606edb7b8`

B5 evidence-freeze commit: `dc09bfb0e8d9d265fe592882713d3c156bcd01ff`

## Outcome

The source-bound image passed two fresh, isolated judge-flow invocations. Each invocation ran with
no network, shared state, bind mount, volume, port publication, inherited credential, AWS call, or
AWS mutation and proved:

```text
APPROVED_FINAL_STATE=SUCCESS_WITH_EVIDENCE
APPROVED_MUTATIONS_BEFORE_DECISION=0
APPROVED_MOCK_MUTATIONS=1
DENIED_FINAL_STATE=DENIED_BY_HUMAN
DENIED_MOCK_MUTATIONS=0
PENDING_APPROVAL_RECOVERED=true
RECOVERY_RECONCILED=true
RECOVERY_MOCK_MUTATIONS=0
REPLAY_REJECTED=true
REPLAY_MUTATION_DELTA=0
RESOURCE_BINDING_TAMPER=REJECTED_FAIL_CLOSED
EXTERNAL_NETWORK_CONNECTIONS=0
PROVIDER_NETWORK_CALLS=0
AWS_CALLS=0
AWS_MUTATIONS=0
```

Both deterministic portable receipts had SHA-256
`f365b07702e43c3848b3470453910b2239d640e8e9ec22a917790a702c110ba3`. The aggregate gate's
internal receipt SHA-256 is
`f9f5861882cba8060ef05fd8f189848b07488dba24912af4f6624d947a503402`. These are local
mock/offline receipts, not live-cloud evidence.

## Image and start contract

```text
LOCAL_REFERENCE=localhost/aioa-portable:b5-cmd-c262c9f25bbe
IMAGE_ID=d5eca6b273309ba0fda6e143af47ea0c9c160a7605b29dd6f1fa8262c8d720e9
LOCAL_MANIFEST_DIGEST=sha256:371b7c5b3bc9d88fe07aba54a5bd4b3e69a526ea1ff313b09253b75983e5856a
CONFIGURED_USER=aioa
CONFIGURED_ENTRYPOINT=NONE
DEFAULT_CMD=python -m aioa_cloudops_agent.portable_server
PLATFORM=linux/amd64
```

The default command preserves ordinary container startup. Render's `dockerCommand` can replace that
CMD, create the operator-token file with mode `0600`, remove `AIOA_OPERATOR_TOKEN` from the child
environment, and then `exec` the same server module. The judge-flow command's `--entrypoint python`
is a deliberate test override for `python -m aioa_cloudops_agent.portable`; it is not a claim about
the Dockerfile's configured Entrypoint.

## Non-root and local-engine boundary

The local Podman 4.9.3 environment has a single host UID/GID mapping and cannot directly execute the
image's declared UID/GID 65532. A failed default-user Podman probe was not counted as passing. The
two disposable judge flows used the gate's narrowly allowed `--user 0:0` compatibility override
only after a fresh image-ID/digest/source-bound non-root proof established:

```text
EFFECTIVE_UID=65532
EFFECTIVE_GID=65532
CAP_EFF=0000000000000000
NO_NEW_PRIVS=1
PID1=python -m aioa_cloudops_agent.portable_server
HEALTH=ok
READINESS=ready
TOKEN_MODE=0600
```

That non-root proof used a private Bubblewrap user namespace against the exact exported image root
filesystem. The machine gate calls this compatibility path `BOUND_EXTERNAL_OCI_RUNTIME`; that is a
schema label, not a claim that the earlier nested-crun attempt succeeded. The operator-local Podman
wrapper only works around an inaccessible parent path inside a private mount namespace. It does not
change the host path, image contents, image privileges, flow mounts, or deployment configuration,
and it is not represented as a declared-user Podman proof. A normal engine is expected to run the
image's declared `aioa` user directly.

## Recertification gates

```text
FULL_PYTEST=PASS 1465 passed 0 failed 0 skipped
FOCUSED_RENDER_B5_TESTS=PASS 23/23
P0=PASS 15/15 136 proof tests
P1=PASS 6/6 93 proof cases
B4=PASS 11/11 43 proof tests
CLEAN_CLONE=PASS 6/6
RUFF=PASS
PACKAGE_BUILD=PASS
PIP_CHECK=PASS
REVIEWER_EVIDENCE=PASS 28 claims 0 live receipts
SOURCE_SECRET_SCAN=PASS 0 findings
IMAGE_PRIVACY_SCAN=PASS 0 findings
CONTAINER_JUDGE_GATE=PASS 2/2
NONROOT_EXACT_ROOTFS_PROOF=PASS
DIFF_CHECK=PASS
```

The first full-suite attempt recorded `1464 passed, 1 failed` because the pinned local AWS CLI
version probe transiently returned unavailable while concurrent workloads were active. AWS CLI
`2.36.11` was present and exact; the isolated test passed. With the workload quiesced, the complete
suite passed `1465/1465`. No test or AWS gate was weakened or changed.

## External-action boundary

```text
AWS_CALLS=0
AWS_MUTATIONS=0
LIVE_DEPLOYMENTS=0
REMOTE_PUSHES=0
IMAGE_PUSHES=0
PUBLICATIONS=0
EMAILS_SENT=0
```

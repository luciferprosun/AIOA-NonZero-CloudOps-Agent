# Portable B5 container judge certification

Date: 2026-09-02 Render startup-script recertification

Phase: B5, clean-clone container judge flows

Render startup-script implementation commit: `af44999efe4bda7aa8b35931377af5eee0b49bbc`

Frozen image-source commit: `797c94e72151c46504b9ae81412738aa6b253e8a`

B5 evidence-freeze commit: `bafe664295ebcf2f67735854fcc36de156abc225`

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
`1b75a75026625a1549d52d855097873e0b6fb969a66c3e75e8ad51351c291aee`. These are local
mock/offline receipts, not live-cloud evidence.

## Image and start contract

```text
LOCAL_REFERENCE=localhost/aioa-portable:b5-render-797c94e72151
IMAGE_ID=2f4b9a0d2708ae82aeda558e45271b59b192894a3b09a1831723ad42e8fe78b4
LOCAL_MANIFEST_DIGEST=sha256:bdf35995e5588ccb93348f0784411d32d0aeb480483b1f34d530c4e3f34edbc3
CONFIGURED_USER=aioa
CONFIGURED_ENTRYPOINT=NONE
DEFAULT_CMD=python -m aioa_cloudops_agent.portable_server
RENDER_START_SCRIPT=/usr/local/bin/aioa-render-start
RENDER_START_SCRIPT_MODE=0555
RENDER_DOCKER_COMMAND=/usr/local/bin/aioa-render-start
PLATFORM=linux/amd64
```

The default command preserves ordinary container startup. Render's `dockerCommand` is the fixed,
single executable path above. The script creates the operator-token file with mode `0600`, removes
`AIOA_OPERATOR_TOKEN` from the child environment, and then `exec`s the same server module without a
multi-command quoting boundary. The judge-flow command's `--entrypoint python`
is a deliberate test override for `python -m aioa_cloudops_agent.portable`; it is not a claim about
the Dockerfile's configured Entrypoint.

## Non-root and local-engine boundary

The local Podman 4.9.3 environment has a single host UID/GID mapping and cannot directly execute the
image's declared UID/GID 65532. A direct default-user Podman diagnostic could not complete under
that mapping and was not counted as passing. The
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
schema label, not a claim that the earlier nested-crun attempt succeeded. The operator-local
accessible wrapper uses local engine state under the dedicated `.aioa-b6` data root and bind-remaps
its storage parent only inside a private user/mount namespace. It does not alter image contents,
image privileges, the judge-flow mount policy, or deployment configuration, and it is not a
declared-user Podman proof. A normal engine is expected to run the image's declared `aioa` user
directly.

## Recertification gates

```text
FULL_PYTEST=PASS 1465 passed 0 failed 0 skipped
FOCUSED_RENDER_START_TESTS=PASS 13/13
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

The complete suite passed `1465/1465` on the first recertification run. The P1 command proof was
re-run from a clean worktree after generated evidence was safely stashed, and passed `6/6`. No
safety, approval, or AWS gate was weakened; the Render-start recertification updated the test
inventory and passed `1465/1465` tests.

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

# W7A Phase 4 — sandbox setup/installer — 2026-09-04

## Gate status

`PHASE_4_RESULT=PARTIAL_DOCKER_UNAVAILABLE`

The safe provider/setup scaffold is committed at
`c257007de55cb7ccf0aef37c2dabb1ac4fc84ae8`. All implemented contracts,
deterministic planners, negative controls, cross-phase boundaries, full regression,
and canonical gates pass. A real Docker executable/daemon is not present on this
host, so no container runtime claim is emitted.

This is the mandated Docker-unavailable outcome from the execution prompt. Docker
was not installed, no host package manager was invoked to install it, no substitute
process isolation was mislabeled as a sandbox, and no rootless/non-root/network-off
runtime proof was fabricated.

Frozen W7/B5/B6 remains unchanged at
`945c87052815b237004d259fe993cc92cbd579b7`. This W7A checkpoint neither modifies
nor recertifies those release artifacts.

## Reuse decisions

- `agent.digest_workspace_tree` supplies the existing bounded, content-addressed
  source-tree identity and rejects links, hardlinks, special files, secret paths,
  excess file count, and excess bytes.
- Workspace jail principles were preserved in the setup manifest reader: canonical
  relative paths, descriptor-relative `O_NOFOLLOW` reads, regular single-link file
  checks, size bounds, and before/after tree identity.
- UUIDv7 identities, `NonZeroContract`, SHA-256 aliases, UTC validation, closed
  enums, provider-neutral redaction, and strict extra-field denial are reused.
- The Phase 2 `OwnedProcess` was not generalized into an unbounded shell. With no
  Docker engine available, no product process runner was introduced merely to make
  a test appear real.

## Provider-neutral surface and lifecycle

`src/aioa_cloudops_agent/sandbox/provider.py::SandboxProvider` exposes the target
surface independently of Docker:

```text
availability
create
stage_repository
setup_environment
exec
read_file
write_file
snapshot
restore
collect_diff
destroy
```

It exposes no GitHub, Git remote, AWS, deployment, host package manager, sudo, or
Docker-daemon administration method. `DockerSandboxProvider` implements the same
surface but fails closed before execution when the engine is missing, invalid, or
not independently certified.

The lifecycle guard admits only:

```text
CREATED -> REPOSITORY_STAGED -> SETUP -> READY
        -> CODING_OFFLINE -> COLLECTING -> DESTROYED
```

Closed failure states are `SETUP_FAILED`, `COMMAND_FAILED`, `POLICY_DENIED`,
`RESOURCE_LIMIT`, `CLEANUP_FAILED`, and `SANDBOX_CRASHED`. A skipped, unknown,
ambiguous, or failure state cannot transition to `READY` or success.

## Docker availability and toolbox truth

Observed host result:

```text
DOCKER_AVAILABILITY=DOCKER_EXECUTABLE_MISSING
DOCKER_RUNTIME_STARTED=NO
DOCKER_INSTALL_ATTEMPTED=NO
SANDBOX_RESOURCES_CREATED=0
TOOLBOX_IMAGE_BUILT=NO
TOOLBOX_IMAGE_IDENTITY=NOT_AVAILABLE
```

`docker`, `podman`, `nerdctl`, and `buildah` were absent from command discovery.
The prompt expressly forbids installing a daemon on the host, so no toolbox image
was built and no image digest is claimed. A future toolbox must supply a matching
`aioa/sandbox-toolbox@sha256:<digest>` reference, digest, source commit, non-root
UID/GID `65532:65532`, required tool inventory, and `secrets_baked_in=false`; tags
alone are rejected.

## Hardened Docker v1 plan

`DOCKER_SANDBOX_V1` is immutable and requires:

- non-root `65532:65532`;
- `privileged=false`;
- `cap-drop=ALL`;
- `no-new-privileges=true`;
- read-only root filesystem;
- no Docker socket, host home, arbitrary bind, SSH/AWS/config/browser/Codex mount;
- a copied repository in an AIOA-owned named volume;
- setup network limited to the package-registry policy;
- coding/test network `NONE`;
- no setup credential by default and no host install;
- CPU `1.0`, memory `512 MiB`, PIDs `128`, open files `1024`, command timeout
  `300s`, and normalized output limit `128 KiB`;
- manifest-only snapshots, never blind `docker commit`.

`DockerCommandPlanBuilder` emits structured argv only. Offline execution includes
`--network=none`; both setup/offline plans include `--read-only`,
`--cap-drop=ALL`, `--security-opt=no-new-privileges:true`, finite resource limits,
the exact non-root user, a tmpfs with `noexec,nosuid,nodev`, and only the owned
workspace volume. Tests reject `--privileged`, Docker socket mounts, host-home
binds, absolute/traversal/hidden paths, `LD_PRELOAD`, `DOCKER_HOST`, credential
variables, shell, sudo, and host package-manager command shapes.

These are validated plans, not runtime proof. In particular, the named
`aioa-w7a-package-registry-only` network still requires a real operator-provisioned
egress-enforcement implementation and runtime certification before it may be used.

## Deterministic setup planner

`src/aioa_cloudops_agent/sandbox/setup.py::DeterministicSetupPlanner` reads only
fixed manifest names from an exact source-tree digest. It never accepts model text,
raw shell, an external manifest path, a package URL, or a custom setup script as
command authority.

Supported Phase 4 plans:

```text
PYTHON_REQUIREMENTS:
python -m pip install --disable-pip-version-check --no-input
  --require-hashes -r requirements.txt

PYTHON_UV:
uv sync --frozen --no-install-project

NODE_NPM:
npm ci --ignore-scripts --no-audit --no-fund
```

Python requirements must use exact `==` pins and at least one lowercase SHA-256
hash per requirement. `uv.lock` and `pyproject.toml` must be a complete,
unambiguous pair and cannot declare an unapproved index. NPM requires matching
`package.json`/`package-lock.json`, lockfile version 2 or 3, and denies non-default
registry/URL/file dependencies. NPM lifecycle scripts are disabled in both argv and
environment.

Each plan binds ecosystem, exact argv, fixed credentialless environment, manifest
paths/sizes/SHA-256 values, repository tree SHA-256, network class, and policy facts
into a canonical plan SHA-256. Changing argv, manifest, source tree, registry,
environment, or authority field invalidates the plan.

Final offline probe from the clean implementation commit:

```text
PYTHON_PLANNER=PASS
PYTHON_PLAN_SHA256=97cd9c53160710216f3eee40a24df036cf5d575c21233c31e444ac46a27c6e5c
PYTHON_RUNTIME_INSTALL=BLOCKED_DOCKER
NODE_PLANNER=PASS
NODE_PLAN_SHA256=2f672b041dd26e6aad33b900ea195c0d45fbf42819b2ed83e82d0ff8476669f4
NODE_RUNTIME_INSTALL=BLOCKED_DOCKER
SETUP_NETWORK_RUNTIME=BLOCKED_DOCKER
CODING_OFFLINE_NETWORK_RUNTIME=BLOCKED_DOCKER
HOST_PYTHON_PACKAGE_INVENTORY_STABLE=YES
HOST_PACKAGE_INSTALLS=0
SANDBOX_GITHUB_CREDENTIALS=0
SANDBOX_AWS_CREDENTIALS=0
SANDBOX_SSH_CREDENTIALS=0
```

No package was installed during this probe. “Planner PASS” is not represented as
“dependency installed”.

## Snapshot and cleanup semantics

`SnapshotRef` supports only `CONTENT_MANIFEST_ONLY`, binds source/environment
digests, and requires `container_image_committed=false` and
`credentials_captured=false`. It cannot restore stale execution authority.

`CleanupReceipt` accepts only an AIOA UUID-owned resource name and requires zero
unrelated resources touched and zero orphans. With Docker unavailable, no sandbox
resource existed to destroy, so runtime cleanup is
`NOT_APPLICABLE_NO_RESOURCES`; only the contract and transition behavior are
tested. A real repeated create/setup/destroy leak proof remains blocked.

## Focused, cross-phase, and regression evidence

- Focused Phase 4 unit suite: `56/56 PASS`.
- Cross-phase integration suite: `2/2 PASS`.
- Combined Phase 4 focused result: `58/58 PASS`.
- Combined focused Phase 2–4/security/static matrix: `136/136 PASS`.
- Full repository regression on exact commit `c257007`: `1850/1850 PASS` in
  `841.55s`.
- P0: `15/15 PASS`, `0 FAIL`, `0 SKIP`.
- P1: `6/6 PASS`, `0 FAIL`, `0 SKIP`, including clean-clone proof.
- B4: `11/11 scenarios PASS`, `43 proof tests`,
  `AWS_CALLS=0`, `AWS_MUTATIONS=0`, `EXTERNAL_NETWORK_CALLS=0`,
  `EXTERNAL_DEPLOYMENTS=0`; private receipt SHA-256
  `f017a70564f5f05feba2cc3528f1d72aa00f5951218fb06a4bf3934e1b3b3ad7`.
- Secret scan before audit: `PASS`, `0 findings`, `515 files scanned`, no values
  emitted; receipt SHA-256
  `4bbb330572b64f982fc0777d822b31a40177254c979218d2ecdfac1e7f031aff`.
- Ruff static analysis: `PASS` for `src`, `scripts`, and `tests`.
- Ruff format check: `PASS` for all Phase 4 changed Python files.
- `pip check`: `PASS`.
- `git diff --check`: `PASS`.
- New Python runtime dependencies: `0`.

## Cross-phase boundary proof

`tests/integration/test_w7a_execution_boundaries.py` composes identities across the
three implemented areas without inventing later-phase authority:

1. a Phase 2 `WorkerTask` is bound to an exact disposable tree and still has zero
   GitHub/AWS authority;
2. a Phase 3 issue is namespaced, provenance-bound, and marked remote-untrusted;
3. a Phase 4 setup plan binds the same source tree but accepts neither the GitHub
   context nor a model-authored command as an extra field;
4. worker and setup environments strip or reject GitHub/AWS/SSH/token variables;
5. `SandboxProvider` exposes no push, patch-apply, remote write, or cloud method.

Generic PatchSet policy, repair loops, Execution Capsules, GitHub branches/commits/
pushes, PR creation, and Phase 5+ features were not implemented.

## Exact blocker and safe completion action

```text
BLOCKER=SANDBOX_DOCKER_EXECUTABLE_MISSING
```

On a separately prepared host where Docker is already safely installed, Phase 4
must be resumed to:

1. build and digest-pin a reviewed Python/Node/git/ripgrep toolbox image;
2. implement and prove the registry-only setup network;
3. run the Python and Node installs inside disposable non-root containers;
4. independently prove UID, capability drop, no-new-privileges, no socket/home/
   credential mounts, finite resource enforcement, and `--network=none` during
   coding/tests;
5. prove diff collection, crash/timeout behavior, manifest-only snapshot semantics,
   and repeated owned-resource cleanup with zero orphans;
6. rerun this full gate before authorizing Phase 5.

## Invariants

```text
SANDBOX_PROVIDER_SCAFFOLD=PASS
DOCKER_SANDBOX_REAL=BLOCKED
DOCKER_INSTALL_ATTEMPTED=NO
SANDBOX_NON_ROOT_PLAN=PASS
SANDBOX_NON_ROOT_RUNTIME=NOT_PROVEN
SANDBOX_PRIVILEGED=NO
SANDBOX_DOCKER_SOCKET_MOUNT=NO
SANDBOX_HOST_HOME_MOUNT=NO
SANDBOX_PYTHON_INSTALL_PROOF=BLOCKED_DOCKER
SANDBOX_NODE_INSTALL_PROOF=BLOCKED_DOCKER
SETUP_NETWORK=UNAVAILABLE
CODING_NETWORK_DEFAULT=NOT_PROVEN
HOST_PACKAGE_INSTALLS=0
PRODUCT_GITHUB_MUTATIONS=0
AWS_CALLS=0
AWS_MUTATIONS=0
DEPLOYMENTS=0
W7_FROZEN_HEAD=945c87052815b237004d259fe993cc92cbd579b7
W7_B5_B6_RECERTIFIED=NO
W8_EXECUTED=NO
PHASE_4_RESULT=PARTIAL_DOCKER_UNAVAILABLE
PHASE_5_AUTHORIZED=NO
```

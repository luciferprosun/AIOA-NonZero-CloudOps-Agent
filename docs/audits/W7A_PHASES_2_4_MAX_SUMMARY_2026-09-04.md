# W7A Phases 2–4 MAX summary — 2026-09-04

## Outcome

`RESULT=PARTIAL`

Phase 2 is fully green with a real Codex App Server worker. Phase 3 is fully green
with a real official GitHub MCP read plane. Phase 4 has a green provider/setup
scaffold and all repository gates, but the host has no Docker executable/daemon;
therefore container execution, dependency installation, network transition,
runtime isolation, and cleanup cannot truthfully be certified.

The exact safe result is:

```text
PHASE_2_RESULT=PASS
PHASE_3_RESULT=PASS
PHASE_4_RESULT=PARTIAL_DOCKER_UNAVAILABLE
PHASE_5_AUTHORIZED=NO
```

## Repository identity and frozen fallback

```text
REPO=/media/l/LSC_DATA/AWS_HACKATHON/AIOA-NonZero-CloudOps-Agent
WORK_BRANCH=codex/w7a-agent-execution-slice
HEAD_START=06f8c1c9dc192827681709b5e6f051ace64e06d2
HEAD_AFTER_PHASE_2=e1e457169d4767a73eca616280d35bb91eba47bf
HEAD_AFTER_PHASE_3=01eb2c3d90735999f197d447c88ad945aad43598
HEAD_AFTER_PHASE_4=11be59928748c6df9ec99383e9bd1195552c926f
FROZEN_W7_BRANCH=codex/w7-final-release-candidate
FROZEN_W7_HEAD_EXPECTED=945c87052815b237004d259fe993cc92cbd579b7
FROZEN_W7_VERIFIED=YES
W7_CHANGED=NO
B5_CHANGED=NO
B6_CHANGED=NO
W8_EXECUTED=NO
B5_B6_RECERTIFICATION_RUN=NO
```

The frozen W7 commit remains an ancestor of the W7A branch. A path-limited diff
from frozen W7 through the Phase 4 checkpoint found no changes to the release
evidence tree, public submission tree, root `Dockerfile`, `render.yaml`, or frozen
build/portable locks.

The final summary commit necessarily cannot contain its own Git SHA. The exact
`HEAD_FINAL` and `REMOTE_HEAD_FINAL` are reported by the post-push machine-readable
handoff after this file is committed.

## Phase 2 — real Codex App Server worker

- Implementation: `src/aioa_cloudops_agent/agent/coding_worker.py::CodingWorker`
  and `src/aioa_cloudops_agent/agent/codex_app_server.py::CodexAppServerWorker`.
- Process boundary: `src/aioa_cloudops_agent/agent/owned_process.py::OwnedProcess`.
- Codex CLI: `codex-cli 0.151.0`.
- App Server protocol: v2 generated schema and negotiated stdio lifecycle.
- Real disposable task: `PASS`; one source correction, local test exit 0, 41
  normalized events, one expected changed file, zero unexpected files.
- Worker GitHub write credentials: `0`.
- Worker AWS credentials: `0`.
- Worker SSH credentials: `0`.
- Runtime GitHub writes: `0`.
- AWS calls: `0`.
- Focused Phase 2 result: `27/27 PASS` after the final owned-process refinement and
  legacy source-security nodes.

Audit:
`docs/audits/W7A_PHASE_2_CODEX_WORKER_APP_SERVER_2026-09-04.md`.

## Phase 3 — real official GitHub MCP read plane

- Implementation:
  `src/aioa_cloudops_agent/github/mcp_read_plane.py::GitHubMcpReadPlane`.
- Official GitHub MCP Server: `v1.0.5`, upstream commit
  `c471ae94bb04059dc26e12c305e219c8fd4299e4`.
- Linux x86_64 executable SHA-256:
  `e38247271e98ea3e0771db747523914b35e37787fa2c120ab6864ee6b4a2c87c`.
- Mode: `--read-only` plus `--lockdown-mode` defense in depth.
- Exact toolsets: `repos,issues,pull_requests,actions`.
- Effective tools: `23`; every tool had `readOnlyHint=true`.
- Effective write tools: `0`.
- Explicit `create_issue` call attempt: denied before transport.
- Real repository metadata/ref proof: `PASS`.
- Real PR list/context: `PASS`, one existing PR.
- Issue list and Actions list: `PASS`; item-level fixtures
  `NOT_APPLICABLE_NO_FIXTURE` and none were created.
- Before/after read context and remote ref: stable.
- Runtime GitHub writes: `0`.
- Focused Phase 3 result: `28/28 PASS`; combined read/security result
  `52/52 PASS`.

Audit:
`docs/audits/W7A_PHASE_3_GITHUB_MCP_READ_PLANE_2026-09-04.md`.

## Phase 4 — safe partial sandbox/setup checkpoint

- Provider interface:
  `src/aioa_cloudops_agent/sandbox/provider.py::SandboxProvider`.
- Docker boundary:
  `src/aioa_cloudops_agent/sandbox/provider.py::DockerSandboxProvider`.
- Setup planner:
  `src/aioa_cloudops_agent/sandbox/setup.py::DeterministicSetupPlanner`.
- Docker availability: `DOCKER_EXECUTABLE_MISSING`.
- Docker sandbox real: `BLOCKED`.
- Host Docker installation attempts: `0`.
- Sandbox resources created: `0`.
- Non-root/container-hardening plan: `PASS`.
- Non-root runtime proof: `NOT_PROVEN_DOCKER_UNAVAILABLE`.
- Privileged requested/used: `NO`.
- Docker socket mount requested/used: `NO`.
- Host-home mount requested/used: `NO`.
- Sandbox GitHub/AWS/SSH credentials: `0/0/0`.
- Host package installs: `0`.
- Python deterministic install plan: `PASS`; runtime install `BLOCKED_DOCKER`.
- Node deterministic install plan: `PASS`; runtime install `BLOCKED_DOCKER`.
- Setup network runtime: `UNAVAILABLE`.
- Coding network default plan: `OFF`; runtime proof `NOT_PROVEN`.
- Runtime cleanup: `NOT_APPLICABLE_NO_RESOURCES`; ownership/cleanup contract tests
  `PASS`.
- Focused Phase 4 result: `58/58 PASS`.
- Combined focused Phase 2–4/security/static matrix: `136/136 PASS`.

Audit:
`docs/audits/W7A_PHASE_4_SANDBOX_SETUP_INSTALLER_2026-09-04.md`.

## Final regression and hardening gates

```text
FULL_REGRESSION_FINAL=1850 passed / 0 failed / 0 skipped / 841.55s
P0_GATE=PASS 15/15
P1_GATE=PASS 6/6 (clean clone included)
B4_OR_CURRENT_HARDENING_GATE=PASS 11/11 scenarios, 43 proof tests
B4_RECEIPT_SHA256=f017a70564f5f05feba2cc3528f1d72aa00f5951218fb06a4bf3934e1b3b3ad7
RUFF_OR_STATIC=PASS
PIP_OR_PACKAGE_CHECK=PASS
SECRET_SCAN=PASS findings=0 files=516
SECRET_SCAN_RECEIPT_SHA256=80c350541e25f06f06e6d29cea31bed14416afb5dcf813f8217f49da344b0195
GIT_DIFF_CHECK=PASS
AWS_CALLS=0
AWS_MUTATIONS=0
DEPLOYMENTS=0
MAIN_PUSHES=0
FORCE_PUSHES=0
TAG_PUBLICATIONS=0
PRODUCT_GITHUB_MUTATIONS=0
```

The 516-file secret receipt is the complete code plus Phase 2/3/4 audit scan taken
immediately before creating this summary. This document cannot recursively embed a
receipt that hashes itself; the post-summary scan and its exact count/digest are
reported in the external final handoff after the summary commit.

## Logical commit staircase

### Phase 2

- `92182d9ec4cbd6c632c2300d6af16eb0c8a92bef` —
  `feat(agent): integrate codex app-server coding worker`
- `e1e457169d4767a73eca616280d35bb91eba47bf` —
  `docs(w7a): record phase 2 certification`

### Phase 3

- `6fd68b446721aad5c406258caca3bac332f624b9` —
  `feat(github): add read-only MCP context plane`
- `01eb2c3d90735999f197d447c88ad945aad43598` —
  `docs(w7a): record phase 3 certification`

### Phase 4

- `c257007de55cb7ccf0aef37c2dabb1ac4fc84ae8` —
  `feat(sandbox): add isolated setup and package installer`
- `11be59928748c6df9ec99383e9bd1195552c926f` —
  `docs(w7a): record phase 4 partial certification`

## Push checkpoints

```text
PHASE_2_PUSH local=e1e457169d4767a73eca616280d35bb91eba47bf remote=e1e457169d4767a73eca616280d35bb91eba47bf verified=YES ahead=0 behind=0
PHASE_3_PUSH local=01eb2c3d90735999f197d447c88ad945aad43598 remote=01eb2c3d90735999f197d447c88ad945aad43598 verified=YES ahead=0 behind=0
PHASE_4_PUSH local=11be59928748c6df9ec99383e9bd1195552c926f remote=11be59928748c6df9ec99383e9bd1195552c926f verified=YES ahead=0 behind=0
```

All pushes were normal non-force pushes to the W7A development branch by the
trusted builder. They are repository-development hygiene, not a product GitHub
write actuator. There were no pushes to main or frozen W7.

## Security findings and residual risks

`SECURITY_FINDINGS=NONE`

Recorded limitations are not hidden findings:

- The builder's existing GitHub credential is broader than the preferred future
  fine-grained read token. It was confined to the trusted MCP validation boundary
  and never passed to worker/sandbox/product runtime.
- The official GitHub MCP binary is pinned to Linux x86_64; other platforms need
  separately reviewed digests.
- Docker absence prevents any claim of real dependency installation or kernel-level
  sandbox isolation. Pure contracts/mocks/plans cannot replace that proof.
- Phase 4's registry-only network must be enforced and independently tested on an
  already prepared Docker host; the name of a Docker network is not proof of its
  egress policy.

## Exact blocker and handoff

```text
BLOCKER=SANDBOX_DOCKER_EXECUTABLE_MISSING
SAFE_NEXT_ACTION=resume Phase 4 on a host where Docker is already safely installed; build/digest-pin the toolbox and execute the full non-root, setup-network, offline-network, Python, Node, crash/resource, diff, snapshot, and cleanup proofs
NEXT_RECOMMENDED_PHASE_AFTER_BLOCKER=W7A_PHASE_5_BOUNDED_PATCHSET_DETERMINISTIC_FILE_POLICY
PHASE_5_AUTHORIZED=NO
STOP_AFTER_PHASE_4=YES
```

Do not install Docker automatically, do not treat a host process as equivalent
isolation, and do not begin Phase 5 until the Phase 4 runtime blocker is cleared and
the full gate is rerun.

## Resumed host addendum — 2026-09-05 Europe/Berlin

The earlier aggregate above remains the historical Docker-unavailable checkpoint.
It was subsequently resumed under the authorized host-unblock prompt. The current
authoritative status is recorded in the appended `Resumed runtime certification`
section of `W7A_PHASE_4_SANDBOX_SETUP_INSTALLER_2026-09-04.md` and the self-hashed
machine receipt `docs/evidence/w7a/phase4-runtime-certification.json`.

```text
PHASE_2_RESULT=PASS
PHASE_3_RESULT=PASS
PHASE_4_RESULT=PASS
PHASE_4_IMPLEMENTATION_SOURCE_COMMIT=1454eec76bd9eaf848a1e784b78ac365d990dc1b
PHASE_4_TOOLBOX_IMAGE_SHA256=7f4e8f00a1ea130d7b30b8371911239f6bf3df4131533faf04df667668739df7
PHASE_4_RECEIPT_SHA256=66f4d1edbccdf88796409f3e6fb8a5058100a6b6817d136f0de4f2a8e256d7e6
FULL_REGRESSION=1863/1863 PASS
P0=15/15 PASS
P1=6/6 PASS
B4=11/11 PASS
SANDBOX_CLEANUP_ORPHANS=0
AWS_CALLS=0
AWS_MUTATIONS=0
DEPLOYMENTS=0
PRODUCT_GITHUB_MUTATIONS=0
PHASE_5_AUTHORIZED=YES
```

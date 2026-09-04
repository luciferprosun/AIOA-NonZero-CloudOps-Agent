# W7A Phases 2–4 preflight — 2026-09-04

## Result

`PREFLIGHT_GATE=PASS`

This checkpoint re-attests the Phase 1 implementation line before executable work begins. It is
not B5/B6 release evidence and does not change the frozen W7 release candidate.

## Git identity and remote state

- Repository: `/media/l/LSC_DATA/AWS_HACKATHON/AIOA-NonZero-CloudOps-Agent`
- Work branch: `codex/w7a-agent-execution-slice`
- Preflight HEAD: `06f8c1c9dc192827681709b5e6f051ace64e06d2`
- Remote work-branch HEAD after read-only fetch: `06f8c1c9dc192827681709b5e6f051ace64e06d2`
- Ahead/behind: `0/0`
- Remote divergence: `NO`
- Frozen fallback branch: `codex/w7-final-release-candidate`
- Frozen W7 HEAD: `945c87052815b237004d259fe993cc92cbd579b7`
- Frozen branch ancestry: verified as an ancestor of the work branch
- Frozen branch remote note: the fallback ref is local; origin does not publish that branch name.
  The immutable commit object and local ref resolve exactly to the required SHA.
- Worktree before implementation: `CLEAN`
- Diff from frozen W7 before this file: only
  `docs/audits/W7A_AGENT_EXECUTION_DISCOVERY_2026-09-04.md`

## Phase 1 authority

- Canonical audit: `docs/audits/W7A_AGENT_EXECUTION_DISCOVERY_2026-09-04.md`
- Phase 1 result: `PASS`
- Discovery domains: `15/15`
- Classification: `PRESENT=3`, `PARTIAL=9`, `MISSING=3`, `CONFLICTING=0`
- `PHASE_2_READY=YES`

## Reuse targets

### Phase 2

- Extend the existing agent/runtime composition without altering frozen tool tuples.
- Reuse `domain.models.ExecutionContext`, Non-Zero identifiers, `ControlResult`, `FailureDetail`,
  checkpoints/audit events, and `WorkspaceRef` identity.
- Keep the App Server adapter transport-only. Normalize its JSON-RPC stream into closed contracts;
  worker output remains non-authoritative candidate data.
- Preserve the existing non-applying patch and exact human-authority boundaries.

### Phase 3

- Put the official GitHub MCP behind an explicit read-only context adapter.
- Allow only repository, issue, pull-request, and Actions reads. Treat all returned text as tainted
  remote data. Keep credentials inside the trusted MCP process and out of worker/sandbox state.
- Add no GitHub mutation method or runtime write credential.

### Phase 4

- Place `DockerSandboxProvider` behind workspace identity and a replaceable `SandboxProvider`
  protocol.
- Reuse the fixed-runner techniques from `scripts/w4_render_start_profile.py`: structured argv,
  bounded output/time, private temporary roots, sanitized environments, and deterministic cleanup.
- Stage a sandbox-owned repository copy. Setup may use bounded network; coding is network-off,
  non-root, non-privileged, capability-dropped, resource-limited, and credentialless.
- Derive package-manager operations only from recognized manifests/lockfiles; no model-supplied or
  repository-supplied arbitrary setup commands.

## Installed protocol/tool discovery

- Codex CLI: `codex-cli 0.151.0`
- App Server transport: `stdio://` default; Unix socket and authenticated WebSocket modes exposed
- Generated current experimental JSON schema: successful in an untracked `/tmp` directory
- Required App Server lifecycle present: `initialize`, `thread/start`, `turn/start`,
  `turn/diff/updated`, `turn/completed`, and `turn/interrupt`
- Git: `2.43.0`
- Python: `3.12.3`
- pytest: `8.4.2`
- Ruff: `0.16.4`
- pip: `26.2.1`
- Node: `18.19.1`
- npm: `9.2.0`
- Docker CLI/daemon: `UNAVAILABLE`
- Official GitHub MCP executable: `UNAVAILABLE`
- pnpm/yarn: `UNAVAILABLE`

Docker and a live official GitHub MCP process are external proof constraints, not permission to
install host packages. The prompt explicitly permits implementation plus offline negative/contract
proofs with truthful partial live status when these external tools are unavailable.

## Fast safety baseline

- Historical targeted cases selected from W3–W6: `15/15 PASS` (nine test nodes, including
  parametrized cases; `10.10s`)
- Ruff focused baseline: `PASS`
- `git diff --check`: `PASS`
- AWS calls: `0`
- Deployments: `0`

## Gate facts

```text
PHASE_1_RESULT=PASS
PHASE_2_READY=YES
W7_FROZEN_HEAD=945c87052815b237004d259fe993cc92cbd579b7
W7_UNCHANGED=YES
B5_UNCHANGED=YES
B6_UNCHANGED=YES
W8_EXECUTED=NO
WORK_BRANCH=codex/w7a-agent-execution-slice
WORKTREE=CLEAN
REMOTE_DIVERGENCE=NO
AWS_CALLS=0
DEPLOYMENTS=0
```

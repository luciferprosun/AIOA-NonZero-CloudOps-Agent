# Deployment pause handoff — 2026-09-02

## Checkpoint status

```text
DEPLOYMENT_TRACK=PAUSED
DEPLOYMENT_PATH_IMPLEMENTED=YES
LIVE_DEPLOYMENT=HUMAN_PENDING
PROVE_DEPLOY_PATH_ONCE=HUMAN_PENDING
CUSTOM_DOMAIN=DEFERRED
D2=DEFERRED
M1=DEFERRED
AUTO_DEPLOY=OFF
D1_2_ACCEPTANCE=DEFERRED_UNTIL_HUMAN_REDEPLOY_AND_URL
D1_3_LIVE_CERTIFICATION=DEFERRED
RESUME_REQUIRES=HUMAN_REDEPLOY_AND_PUBLIC_URL_OR_NEW_EXPLICIT_INSTRUCTION
AWS_MUTATIONS=0
PAID_RESOURCES=0
EXTERNAL_DEPLOYMENTS_DURING_RECERTIFICATION=0
CHECKPOINT_BRANCH=codex/portable-d1-d2-m1-overnight
CERTIFIED_RUN_HEAD=060ef535fc7bc02ec71c333478333f7340c624e4
CERTIFIED_RUN_WORKTREE=CLEAN
```

`CERTIFIED_RUN_HEAD` is the pushed B5/B6 recertification head immediately before this handoff
report. The final handoff commit is intentionally identified by Git rather than embedded in its own
content; the exact pushed checkpoint HEAD must be reported by the closing command output.

The deployment track is paused after implementing and locally proving one Render deployment path.
This checkpoint does not authorize a redeploy, a provider configuration change, a new service, a
custom domain, DNS work, D2, M1, AWS activity, or paid resources.

## Completed recertification gates

| Gate | Result |
| --- | --- |
| Full regression | PASS — 1,465/1,465, zero failures or skips |
| P0 | PASS — 15/15 gates, 136 proof tests |
| P1 | PASS — 6/6 gates, 93 proof tests |
| B4 hardening | PASS — 11/11 scenarios, 43 proof tests |
| Clean clone | PASS — 6/6 checks against the exact final recertification head |
| B5 BUILD_COMPLETE | PASS — exact source/image/digest evidence verifies |
| B6 PUBLICATION_READY | PASS — sanitized clean-room and deterministic bundle recertified |
| Render startup script | PASS — canonical child argv, token `0600`, secret removed from child environment |
| Local `/health` and `/ready` | PASS |
| Non-root exact-rootfs proof | PASS — UID/GID 65532, zero capabilities, `NoNewPrivs=1`, server PID 1 |
| Container judge | PASS — approve, deny, recovery, replay, and binding rejection in 2/2 isolated runs |
| Source secret scan | PASS — 418 files, zero findings |
| B6 public privacy scan | PASS — zero findings, two byte-identical final archives |
| Render official schema | PASS — zero errors |
| Ruff / pip check / diff check | PASS / PASS / PASS |
| AWS mutations / paid resources | 0 / 0 |

Authoritative evidence remains in:

- `docs/evidence/release/portable-b5-build-complete-attestation.json`
- `docs/evidence/submission/portable-b6-reproducibility.json`
- `docs/evidence/submission/portable-b6-publication-bundle.json`
- `docs/audits/PORTABLE_B5_BUILD_COMPLETE_RELEASE_CANDIDATE_2026-09-01.md`
- `docs/audits/PORTABLE_B6_PUBLICATION_READY_2026-09-01.md`
- `docs/audits/PORTABLE_D1_NON_AWS_LIVE_DEPLOYMENT_2026-09-02.md`

## Preserved deployment boundary

The following reviewed files are frozen at this checkpoint:

| Preserved item | SHA-256 |
| --- | --- |
| `render.yaml` | `c9e351188844ec4236068ffe62fa9747376ec520eabea39c9e92dd30909a645c` |
| `scripts/render_start.sh` | `d350917c132a338605f630fde97a2ac017e1664fe9cf413a7153827326e6d250` |
| `Dockerfile` | `4640463904ced78776f5f482510e9f117d7ee2e0b6a8e04c5ba83e349378bc8f` |
| `.dockerignore` | `0e6b8400e2813f0be52a5f3f5243d520cbbe740b286a44749e8e6db368265812` |
| `docs/operations/non-aws-live-deployment.md` | `27ee7385db09d69f38472d10ce19b02fe5f594fcaa7ad8506984ec1985828c9e` |
| `docs/audits/PORTABLE_D1_NON_AWS_LIVE_DEPLOYMENT_2026-09-02.md` | `1551f26037c3a1b574eb3fd334b68f03e96df0ea7d34d2d9025477c1f6069d9d` |
| `docs/evidence/deployment/portable-d1-target-decision.json` | `70d5c7344c38f3d6f5196eae1751990cfa34b168048bdbe61907f65dc1bfe8ae` |
| `docs/operations/phase3-rollback-cleanup.md` | `37d5d48ca4c88ed0e90a89795d065ba72fd134d1aa14f5755cd7e524895bf198` |

The active Render contract remains one Free Web Service in Frankfurt, the mock provider, AWS
disabled, no allowed egress, human approval required, `/ready` health check, automatic deploy off,
and exactly:

```text
dockerCommand: /usr/local/bin/aioa-render-start
```

No further deployment hardening is scheduled. Changes to any frozen runtime or deployment input
require explicit authorization and would invalidate the applicable certification boundary.

Broader active-sequence language in the preserved D1 audit and runbook is now dormant and
superseded by this pause authority. In particular, do not run the full live acceptance harness,
session/token exchange, approve/deny/replay flows, restart/cold-start tests, or a proactive rollback
drill under `PROVE_DEPLOY_PATH_ONCE`.

## Exact human-pending deployment actions

Only these actions remain for `PROVE_DEPLOY_PATH_ONCE`:

1. A human decides whether to redeploy the existing Render service from the pushed branch. Do not
   create a second service or any additional provider resource.
2. In the Render dashboard, the human confirms the existing service remains Free and Frankfurt,
   with no paid disk, database, worker, custom domain, card requirement, or other resource.
3. The human supplies or confirms the `sync: false` operator token without exposing it in chat,
   Git, command history, logs, or URLs. Sync the Blueprint once; if that starts deployment, do not
   trigger a second manual deploy. Otherwise, trigger exactly one redeploy of the existing service.
4. The human provides the resulting public HTTPS origin and exact deployed Git revision/source
   identity.
5. Only after that input, an agent may perform one minimal read-only smoke verification using GET
   requests and read-only provider metadata/logs: HTTPS reachable, `/health` PASS, `/ready` PASS,
   and deployed source identity confirmed. Do not run the broader acceptance harness because it
   performs session POST requests.
6. Record `PROVE_DEPLOY_PATH_ONCE=PASS|FAIL` and stop. A failed smoke is reported as evidence; it
   does not authorize additional engineering, provider changes, or resource creation.

If the human needs rollback after their redeploy, the preserved Render rollback instructions in
`docs/operations/non-aws-live-deployment.md` remain available. Executing rollback is a separate
human/provider action and is outside this paused agent track unless explicitly authorized.

## Explicitly deferred work

```text
FURTHER_RENDER_ENGINEERING=DEFERRED
DEPLOYMENT_HARDENING=DEFERRED
CUSTOM_DOMAIN=DEFERRED
DNS=DEFERRED
D2=DEFERRED
M1=DEFERRED
ADDITIONAL_PROVIDER_RESOURCES=FORBIDDEN_WITHOUT_NEW_AUTHORIZATION
```

The new primary engineering direction is the audited AIOA Codex-grade executability roadmap.
Bounded process execution, workspace/filesystem capabilities, Git and dependency operations,
long-running execution, isolation, browser/MCP adapters, capability discovery, receipts,
independent verification, approval classes, and resumable autonomous runs are candidate audit
topics only. None is authorized for implementation by this handoff.

`M1=DEFERRED` refers to the upcoming deployment-program milestone named in the new handoff. It does
not rewrite or invalidate the already completed historical Day-15 M1/M2 recovery evidence.

Wait for the new multi-model architecture audit and its approved roadmap.

## Checkpoint closure validation

This handoff changes documentation only; no certified runtime, deployment, application, test, or
evidence input was modified. Before committing the handoff, the deterministic B5 evidence verifier
returned `PASS` for all four artifacts with zero AWS mutations and zero remote pushes; the three
authoritative B6 submission JSON files parsed successfully; the repository secret scan checked 419
files with zero findings, zero network connections, and zero AWS mutations; and `git diff --check`
passed.

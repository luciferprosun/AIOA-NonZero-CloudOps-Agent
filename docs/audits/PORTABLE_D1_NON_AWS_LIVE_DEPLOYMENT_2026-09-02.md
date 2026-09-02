# Portable D1 non-AWS live deployment audit

Date: 2026-09-02

## Main re-attestation

```text
MAIN_REATTESTED=YES
PR_STATE=MERGED
MAIN_HEAD=4fafed8b1a877e55d96ddd9baea0a737fbeeaa4a
ORIGIN_MAIN_HEAD=4fafed8b1a877e55d96ddd9baea0a737fbeeaa4a
MAIN_AHEAD=0
MAIN_BEHIND=0
B5_BUILD_COMPLETE=PASS
B6_PUBLICATION_READY=PASS
WORKTREE=CLEAN
READY_FOR_D1=YES
```

The source PDF contains `4fafed8b1a877e55d96ddd9baea0a737fbeaaa4a`; that value is a typo.
Git and merged PR #1 independently resolve the actual merge commit shown above. The prior full
regression was `1447 passed`, zero failed, zero skipped; P0 was 15/15, P1 was 6/6, and the B4 gate
was 11/11 scenarios with 43 proof tests. Clean-clone, sanitized clean-room, and secret scans passed
with zero findings. At this preflight the B5 evidence validator passed again, 28
deployment-critical tests passed, and `pip check` reported no broken requirements.

Frozen input hashes:

| Input | SHA-256 |
| --- | --- |
| `Dockerfile` | `62ab24342fb35961e6b5b05969f3749b3d4d201afd4f6510223b870c0f4ba93c` |
| `docs/PORTABLE_RUNTIME.md` | `c5af5e77349a1038d860f3108a2bbaee6fbb6d3df7340f931095551a72240233` |
| `docs/submission/demo-runbook.md` | `3ee0e75aab70b9e63860e7deb3e5785cfd6a1df9ac60ea9462d9022fe61d3f47` |

## D1.1 target decision

```text
DEPLOY_PROVIDER=Render
DEPLOY_PLAN=free
DEPLOY_REGION=frankfurt
ACCOUNT_STATE=GITHUB_CONNECTED_HUMAN_DEPLOY_PENDING
PAID_RESOURCE_CREATED=NO
AWS_RESOURCE_CREATED=NO
D1_1_GATE=PASS
```

Render was selected from current official documentation because its Free Web Service supports a
Docker build, public managed HTTPS, environment secrets, log streams, HTTP health checks, restart,
and rollback to the two most recent deployments. Render explicitly documents behavior for
workspaces without a payment method: usage exhaustion suspends services/builds instead of charging
them. The limitations are accepted for this demo: 0.1 CPU, 512 MB RAM, idle spin-down, cold start,
and ephemeral local files.

The deployment contract, secret bootstrap, state semantics, rejected alternatives, and rollback
plan are in `docs/operations/non-aws-live-deployment.md`. Machine-readable decision evidence is in
`docs/evidence/deployment/portable-d1-target-decision.json`. The Blueprint passed Render's current
official JSON Schema. A local launch-contract probe also proved that its `dockerCommand` creates the
operator token at mode 0600, removes the bootstrap secret from the application process environment,
and reaches healthy/ready portable/mock service state. The checkpoint regression passed 24 focused
portable/container/judge tests, Ruff, `pip check`, and the B5 drift validator. The tracked secret
scan inspected 413 files with zero findings and emitted receipt
`87f106ce2a93c43918d727af0a8f2a6a191a7ee0fd35cb11a8fdcc0a1865cc0a`.

No service, deployment, public URL, card, payment commitment, AWS resource, database, disk, or other
provider resource existed at this checkpoint. The human connected Render to GitHub and explicitly
deferred the actual deployment until morning; subsequent work is CLI-only.

## D1.2 live launch

Status: `NOT_STARTED`.

## D1.3 live certification and freeze

Status: `NOT_STARTED`.

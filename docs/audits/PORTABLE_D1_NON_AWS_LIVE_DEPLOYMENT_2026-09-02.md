# Portable D1 non-AWS live deployment audit

Date: 2026-09-02

## Current pre-redeployment state

```text
HISTORICAL_MERGED_MAIN_HEAD=4fafed8b1a877e55d96ddd9baea0a737fbeeaa4a
CURRENT_WORK_BRANCH=codex/portable-d1-d2-m1-overnight
CERTIFIED_RUNTIME_SOURCE=797c94e72151c46504b9ae81412738aa6b253e8a
CERTIFIED_B6_SOURCE=a7bb1d6eb7ff5a86126f02af6758f0298289816b
B5_BUILD_COMPLETE=PASS
B6_PUBLICATION_READY=PASS
RENDER_START_SCRIPT=PASS
READY_FOR_RENDER_REDEPLOY=YES
LIVE_DEPLOYMENT_PERFORMED=NO
```

The earlier `main` merge and its CMD-era D1 evidence remain historical. The Render startup-script
change invalidated the prior image and B6 bundle, so they were not relabeled. B5 was rebuilt from a
clean clone and passed the full 1,465-test regression, P0 15/15, P1 6/6, B4 11/11, clean-clone,
container judge, non-root, pip, Ruff, secret/privacy, and zero-egress gates. B6 was then rebuilt from
the sanitized source and passed deterministic export, no-cache image build, exact startup-script,
non-root PID-1, judge-flow, final privacy, and byte-identical bundle gates.

Frozen inputs:

| Input | SHA-256 |
| --- | --- |
| `Dockerfile` | `4640463904ced78776f5f482510e9f117d7ee2e0b6a8e04c5ba83e349378bc8f` |
| `.dockerignore` | `0e6b8400e2813f0be52a5f3f5243d520cbbe740b286a44749e8e6db368265812` |
| `scripts/render_start.sh` | `d350917c132a338605f630fde97a2ac017e1664fe9cf413a7153827326e6d250` |
| `render.yaml` | `c9e351188844ec4236068ffe62fa9747376ec520eabea39c9e92dd30909a645c` |
| `docs/PORTABLE_RUNTIME.md` | `c5af5e77349a1038d860f3108a2bbaee6fbb6d3df7340f931095551a72240233` |
| `docs/submission/demo-runbook.md` | `3ee0e75aab70b9e63860e7deb3e5785cfd6a1df9ac60ea9462d9022fe61d3f47` |

## D1.1 target decision

```text
DEPLOY_PROVIDER=Render
DEPLOY_PLAN=free
DEPLOY_REGION=frankfurt
ACCOUNT_STATE=GITHUB_CONNECTED_OWNER_REDEPLOY_PENDING
PAID_RESOURCE_CREATED=NO
AWS_RESOURCE_CREATED=NO
D1_1_LOCAL_GATE=PASS
```

The checked-in Blueprint preserves `plan: free`, `region: frankfurt`, `/ready`, the mock provider,
AWS disabled, no allowed egress, and human approval authority. Its only startup override is:

```text
dockerCommand: /usr/local/bin/aioa-render-start
```

The Blueprint passed the current official Render JSON Schema with zero validation errors; the
fetched schema SHA-256 was
`f6cb3fbae8c598d41385069bf7084293b48b802f88e1bc98b1c4b9c24a15be47`.

The installed script proof used the exact clean-room image. It wrote a synthetic operator token to
the configured file at mode `0600`, removed `AIOA_OPERATOR_TOKEN` from the canonical child process,
started `python -m aioa_cloudops_agent.portable_server`, and reached `/health` and `/ready` with all
AWS, external-network, and real-cloud mutation authority disabled. Missing-token startup failed
closed with exit status 2. A separate exact-rootfs proof ran the same contract at UID/GID 65532,
zero capabilities, `NoNewPrivs=1`, and server PID 1.

The provider decision and current hashes are recorded in
`docs/evidence/deployment/portable-d1-target-decision.json`. No Render service or other provider
resource was created or modified by this recertification.

## D1.2 post-redeployment acceptance

Status: `WAITING_FOR_OWNER_RENDER_REDEPLOY`.

The provider-agnostic acceptance harness remains at
`scripts/operations/run_live_acceptance.py`. The checked-in
`docs/evidence/deployment/portable-d1-cli-acceptance.json` is a historical local CMD-era receipt and
is not presented as evidence for the new live deployment. After the owner redeploys the reviewed
Blueprint, D1 must generate a fresh live receipt against the resulting HTTPS origin and exact
deployed revision.

The live acceptance must prove safe health, readiness, unknown-route and unsupported-method
rejection, unauthenticated denial, Bearer-to-session bootstrap, authenticated cookie-session
lookup, TLS verification, deployed source identity, and the expected `Secure`, `HttpOnly`,
`SameSite=Strict` session boundary. It must not print or persist the operator token or session cookie.

```text
LIVE_PUBLIC_URL=EXISTING_PROVIDER_STATE_NOT_INSPECTED
LIVE_HTTPS_REQUESTS=0
AWS_CALLS=0
AWS_MUTATIONS=0
BROWSER_ACTIONS=0
PROVIDER_RESOURCE_CREATION=0
```

## D1.3 live certification and freeze

Status: `BLOCKED_UNTIL_OWNER_REDEPLOYS`.

Approve, deny, replay, binding-tamper, cold-start, deployed-source, and rollback checks have not been
run against the repaired public service in this task. No CLI deployment or provider mutation was
authorized. The repository is locally ready for the owner-triggered Render redeploy; live D1/D2
evidence must be generated afterward.

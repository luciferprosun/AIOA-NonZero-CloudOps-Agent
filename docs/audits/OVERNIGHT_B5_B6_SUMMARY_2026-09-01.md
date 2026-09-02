# Overnight B5/B6 summary

## Historical B5/B6 staircase

The original five-commit B5/B6 certification remains part of repository history:

| # | Historical unit | Commit | Historical gate |
| ---: | --- | --- | --- |
| 1 | B5.1 container runtime and contract | `d18f945a1484a1255339a3b4bcb1560c58d06d9b` | PASS |
| 2 | B5.2 clean-clone container judge flow | `dbea5411b1c0d81de0035d9ef08e28211fb79e79` | PASS |
| 3 | B5.3 build-complete freeze | `e66f05914d6de7fd9b5f5f76faef0fe5c0d19d65` | PASS |
| 4 | B6.1 sanitized public submission package | `c7fa5a5c2509cccf071a9e58477776c1a1e00aea` | superseded |
| 5 | B6.2 publication-ready reproducibility | historical following commit | superseded |

The prior B6 result was invalidated when the Docker start contract changed. Its hashes and image
identity must not be reused for the CMD-recertified release.

## CMD recertification staircase

| Stage | Commit | Status |
| --- | --- | --- |
| Render-compatible Docker start contract and focused proof | `5d10229d9ca0d243068c0ee77a0c90a4e722689c` | PASS |
| frozen B5 image source and re-anchored reviewer evidence | `c262c9f25bbe069f17a05da7221dbce606edb7b8` | PASS |
| regenerated B5 machine evidence | `dc09bfb0e8d9d265fe592882713d3c156bcd01ff` | PASS |
| public-document rebase on CMD-certified B5 | `00f57217b74f3e3c1afa271ea102b7d744b9dbce` | PASS |
| final sanitized B6 source and reserved-test-TLD scanner proof | `46ce221e81f88d82df75d67e144d9a2231c54d64` | PASS |
| clean-room reproducibility receipt | `986c5b2d174e9e745338b141e3f37b1c28ca2997` | PASS |
| final scan, bundle receipt, and audits | this commit | PASS |

## Current B5 outcome

```text
B5=PASS
BUILD_COMPLETE=PASS
SOURCE_COMMIT=c262c9f25bbe069f17a05da7221dbce606edb7b8
IMAGE_ID=d5eca6b273309ba0fda6e143af47ea0c9c160a7605b29dd6f1fa8262c8d720e9
IMAGE_DIGEST=sha256:371b7c5b3bc9d88fe07aba54a5bd4b3e69a526ea1ff313b09253b75983e5856a
CONFIGURED_ENTRYPOINT=NONE
DEFAULT_CMD=python -m aioa_cloudops_agent.portable_server
FULL_PYTEST=PASS 1465/1465
P0=PASS 15/15
P1=PASS 6/6
B4=PASS 11/11
SECRET_SCAN=PASS
AWS_CALLS=0
AWS_MUTATIONS=0
EXTERNAL_DEPLOYMENTS=0
```

The Render bootstrap proof passed locally: a synthetic operator token was written to the configured
file with mode `0600`, removed from the child environment, and followed by the exact canonical
server process reaching `/health` and `/ready`. Missing-token startup failed closed.

## Current B6 outcome

```text
B6=PASS
PUBLICATION_READY=PASS
PUBLIC_SOURCE_COMMIT=46ce221e81f88d82df75d67e144d9a2231c54d64
CONFIGURED_ENTRYPOINT=NONE
DEFAULT_CMD=python -m aioa_cloudops_agent.portable_server
CLEAN_ROOM_NO_CACHE_BUILD=PASS
DEFAULT_CMD_START=PASS
HEALTH_READY=PASS
APPROVE_DENY_RECOVERY_REPLAY=PASS
PUBLIC_SCAN=PASS 0 findings
FINAL_ARCHIVE_SHA256=297136b4d166661608e0e9c0a332b428ffdefe187f6810b177d57b68ae63610a
DETERMINISTIC_FINAL_BUILDS=2/2 IDENTICAL
```

All old B6 identities are superseded. The authoritative B6 report, final scan, and bundle receipt
are the CMD-recertified files under `docs/evidence/submission/`.

## External-action boundary

```text
AWS_CALLS=0
AWS_MUTATIONS=0
EXTERNAL_DEPLOYMENTS=0
REMOTE_PUSHES=0
PUBLICATION_ACTIONS=0
```

No AWS account, Render resource, registry, public endpoint, browser session, email, video platform,
or submission portal was touched. The branch can be pushed after final regression, but deployment
remains a separate owner-authorized step.

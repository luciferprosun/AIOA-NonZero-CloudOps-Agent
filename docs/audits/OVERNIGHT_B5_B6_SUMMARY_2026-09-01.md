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

## Prior CMD recertification staircase

| Stage | Commit | Status |
| --- | --- | --- |
| Render-compatible Docker start contract and focused proof | `5d10229d9ca0d243068c0ee77a0c90a4e722689c` | PASS |
| frozen B5 image source and re-anchored reviewer evidence | `c262c9f25bbe069f17a05da7221dbce606edb7b8` | PASS |
| regenerated B5 machine evidence | `dc09bfb0e8d9d265fe592882713d3c156bcd01ff` | PASS |
| public-document rebase on CMD-certified B5 | `00f57217b74f3e3c1afa271ea102b7d744b9dbce` | PASS |
| final sanitized B6 source and reserved-test-TLD scanner proof | `46ce221e81f88d82df75d67e144d9a2231c54d64` | PASS |
| clean-room reproducibility receipt | `986c5b2d174e9e745338b141e3f37b1c28ca2997` | PASS |
| final scan, bundle receipt, and audits | this commit | PASS |

That staircase is preserved as history. The later Render startup-script change invalidated its B5
image identity and every B6 bundle/image hash.

## Render startup-script recertification staircase

| Stage | Commit | Status |
| --- | --- | --- |
| fixed Render startup executable and focused proof | `af44999efe4bda7aa8b35931377af5eee0b49bbc` | PASS |
| frozen B5 image source and re-anchored reviewer evidence | `797c94e72151c46504b9ae81412738aa6b253e8a` | PASS |
| regenerated B5 machine evidence | `bafe664295ebcf2f67735854fcc36de156abc225` | PASS |
| frozen sanitized B6 source | `a7bb1d6eb7ff5a86126f02af6758f0298289816b` | PASS |
| clean-room image, Render bootstrap, non-root, judge, and reproducibility receipt | `b69fbfda9cb5d0244f55938755312ac820bf0e0e` | PASS |
| final deterministic bundle, privacy scan, and audits | this commit | PASS |

## Current B5 outcome

```text
B5=PASS
BUILD_COMPLETE=PASS
SOURCE_COMMIT=797c94e72151c46504b9ae81412738aa6b253e8a
IMAGE_ID=2f4b9a0d2708ae82aeda558e45271b59b192894a3b09a1831723ad42e8fe78b4
IMAGE_DIGEST=sha256:bdf35995e5588ccb93348f0784411d32d0aeb480483b1f34d530c4e3f34edbc3
CONFIGURED_ENTRYPOINT=NONE
DEFAULT_CMD=python -m aioa_cloudops_agent.portable_server
RENDER_START_SCRIPT=/usr/local/bin/aioa-render-start
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
SOURCE_COMMIT=a7bb1d6eb7ff5a86126f02af6758f0298289816b
IMAGE_ID=a310690a3d411ea133ba2e6aedb05fc9a4279ee7f0a8f16c4ddc198b3d945833
IMAGE_DIGEST=sha256:6602875706bfdbd68444ac83c928d758781aaac8ab9b4358e87d3f7e3f49f9d5
RENDER_START_SCRIPT=PASS
NONROOT_PID1=PASS UID_GID_65532
CONTAINER_JUDGE=PASS 2/2
PUBLIC_SCAN=PASS 0 findings
ARCHIVE_SHA256=af07a6a4c085db60ebd66971bbe5ed42fb3aa7de5d6b7486ffc70b59943bf45a
DETERMINISTIC_REBUILDS=2/2 IDENTICAL
```

The final local bundle is publication-ready but remains unuploaded. Deployment and external
publication are not part of B6.

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

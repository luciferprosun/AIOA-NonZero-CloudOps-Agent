# BUILD_COMPLETE attestation — CMD recertified 2026-09-02

## Attested status

```text
BUILD_COMPLETE=PASS
ATTESTATION_STATUS=BUILD_COMPLETE
SOURCE_COMMIT=c262c9f25bbe069f17a05da7221dbce606edb7b8
SOURCE_TREE=def4ccbb9bb07f6843f8efb2e48c86c1741e8ac3
EVIDENCE_FREEZE_COMMIT=dc09bfb0e8d9d265fe592882713d3c156bcd01ff
CONTAINER_DIGEST=sha256:371b7c5b3bc9d88fe07aba54a5bd4b3e69a526ea1ff313b09253b75983e5856a
CONTAINER_ID=d5eca6b273309ba0fda6e143af47ea0c9c160a7605b29dd6f1fa8262c8d720e9
CONFIGURED_ENTRYPOINT=NONE
DEFAULT_CMD=python -m aioa_cloudops_agent.portable_server
ATTESTATION_SHA256=5106f99fb3ebfe38d1fde9895b85782ee89a686c2e2fd30db5ba2da62de16e43
AWS_CALLS=0
AWS_MUTATIONS=0
DEPLOYMENTS=0
IMAGE_PUSHES=0
REMOTE_GIT_PUSHES=0
PUBLICATIONS=0
LIVE_RECEIPTS=0
```

This attests only to a locally built and locally executed portable/mock artifact. The exact clean
source, hash-pinned inputs, image identity, two ephemeral judge flows, non-root exact-root-filesystem
proof, package manifest, image-export privacy scan, and local test gates are bound by the
machine-readable files in `docs/evidence/release/`.

The local Podman host could not map the declared image UID/GID 65532. The successful non-root proof
therefore used a private Bubblewrap user namespace against the exact exported image root filesystem;
the judge flows used a disclosed `0:0` engine compatibility override only after that proof. This is
not represented as a successful declared-user Podman run or a successful nested-crun run. It does
not change the normal image contract: configured user `aioa`, no fixed Entrypoint, and the canonical
server as default CMD.

This attestation does not assert registry publication, a live container host, public endpoint,
production identity, AWS account access, Bedrock access, cloud mutation, or externally submitted
hackathon entry. The local OCI manifest digest is not described as a registry digest.

## Machine authority

The canonical authority is
`docs/evidence/release/portable-b5-build-complete-attestation.json`. Its compact canonical material
excluding `attestation_sha256` hashes to the value above. Its bound artifact-manifest file SHA-256
is `765f917d8a1eee038d3f4deefdc858cd7785838b0f5039091584950ec396f442`; its deterministic sums-file
SHA-256 is `8f4927a87f0adb2aa2beb737faa483adb64cbaa3f8ceea2b494d1de685a136df`.

Run the offline verifier from a clean checkout with:

```bash
.venv/bin/python scripts/build_b5_release_evidence.py --check --json
.venv/bin/python scripts/validate_reviewer_evidence_manifest.py
```

Any bound drift causes failure. The machine attestation's freeze rule requires a full B5 rebuild and
recertification after any runtime, dependency, container, or bound-document change.

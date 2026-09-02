# BUILD_COMPLETE attestation — Render startup script recertified 2026-09-02

## Attested status

```text
BUILD_COMPLETE=PASS
ATTESTATION_STATUS=BUILD_COMPLETE
SOURCE_COMMIT=797c94e72151c46504b9ae81412738aa6b253e8a
SOURCE_TREE=bd9997296560aa9e57d5fa38001a40a7c38f6a38
EVIDENCE_FREEZE_COMMIT=PENDING_CURRENT_RECERTIFICATION_COMMIT
CONTAINER_DIGEST=sha256:bdf35995e5588ccb93348f0784411d32d0aeb480483b1f34d530c4e3f34edbc3
CONTAINER_ID=2f4b9a0d2708ae82aeda558e45271b59b192894a3b09a1831723ad42e8fe78b4
CONFIGURED_ENTRYPOINT=NONE
DEFAULT_CMD=python -m aioa_cloudops_agent.portable_server
RENDER_START_SCRIPT=/usr/local/bin/aioa-render-start
RENDER_DOCKER_COMMAND=/usr/local/bin/aioa-render-start
ATTESTATION_SHA256=5e2c929f9ede0ac16193c4cbef847d1a96fc8207f5dcac009c5dcbf5fdcdaaa7
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
not change the normal image contract: configured user `aioa`, no fixed Entrypoint, the canonical
server as default CMD, and a fixed Render startup executable with no multi-command quoting boundary.

This attestation does not assert registry publication, a live container host, public endpoint,
production identity, AWS account access, Bedrock access, cloud mutation, or externally submitted
hackathon entry. The local OCI manifest digest is not described as a registry digest.

## Machine authority

The canonical authority is
`docs/evidence/release/portable-b5-build-complete-attestation.json`. Its compact canonical material
excluding `attestation_sha256` hashes to the value above. Its bound artifact-manifest file SHA-256
is `98846b9723e1921ca2b60b8f47a90f3bb7a04c5de9d529a2359e115ff177e8c3`; its deterministic sums-file
SHA-256 is `042ac6cc58d8cc2cc0ac92b25cd9d2cafbce0660c960ab3a77d7c3de7e1fe4dd`.

Run the offline verifier from a clean checkout with:

```bash
.venv/bin/python scripts/build_b5_release_evidence.py --check --json
.venv/bin/python scripts/validate_reviewer_evidence_manifest.py
```

Any bound drift causes failure. The machine attestation's freeze rule requires a full B5 rebuild and
recertification after any runtime, dependency, container, or bound-document change.

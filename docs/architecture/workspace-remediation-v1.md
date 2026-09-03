# WORKSPACE_REMEDIATION_V1 architecture

## Status and purpose

Phase W1 provides a sealed, deterministic, read-only workspace for investigating one sanitized
deployment incident. Phase W2 extends only that additive profile with one deterministic,
proof-carrying patch proposal. The proposal is constructed in memory and is inert: it neither
applies bytes nor grants authority to do so. Neither phase migrates or alters the canonical
CloudOps agent or exposes a general execution platform.

The governing invariant is unchanged:

```text
MODEL_OUTPUT != EXECUTION_AUTHORITY
PATCH_PROPOSAL != PATCH_AUTHORITY
PATCH_PREVIEW != FILE_MUTATION
```

The sealed workspace authority envelope still contains only inspect, list, bounded read, and
SHA-256 hash operations. W2 composes those observations into proposal data without adding a
workspace mutation operation. All path scope, identity, quotas, fixture selection, transformation,
canonical serialization, and policy decisions remain server-owned.

## Component boundary

```text
trusted sanitized fixture
        |
        v
server materializer -> WorkspaceRef + private immutable copy
        |
        v
WorkspaceJail -> WorkspaceEvidenceService -> four evidence tools ---+
        |                    |                                      |
        |                    +-> typed receipt/timeline              v
        +-> canonical path, inode, type, size, link and digest revalidation
                                                     W2 proposal builder
                                                             |
                                                             v
                                    fifth inert Strands tool -> exact preview
```

The model sees opaque run/workspace identity and relative artifact names. It never receives or
selects the server root. The new package is isolated under
`src/aioa_cloudops_agent/workspace/`; there is no dynamic capability registry.

## Fixed capability profile

`WORKSPACE_REMEDIATION_V1` version `1` is an immutable Pydantic contract with these server-owned
bounds:

| Property | Value |
| --- | --- |
| allowed artifacts | `README.md`, `deployment.log`, `expected_runtime_contract.json`, `render.yaml`, `scripts/render_start.sh` |
| maximum files | 5 |
| maximum file size | 32 KiB |
| maximum returned read | 4 KiB |
| operations | `INSPECT`, `LIST`, `READ`, `HASH` |
| mutation allowed | false |
| network allowed | false |

Contract validation rejects extra fields, reordered/expanded operations, duplicate or unsorted
artifact allowlists, and client attempts to enlarge limits. W1 does not provide a profile registry
or a model-selectable profile.

## Contracts and identity binding

- `WorkspaceRef` binds UUIDv7 run and workspace identities to a fixture version and equal source /
  materialized root digests.
- `WorkspaceArtifactRef` binds a canonical relative path to type, byte size, SHA-256, and link
  count.
- `WorkspacePolicyDecision` records an explicit `ALLOW` or `DENY`, stable reason code, operation,
  workspace identity, and immutable no-network/no-mutation authority.
- `WorkspaceObservation` exposes bounded incident symptoms and the exact evidence set without
  supplying a diagnosis.
- `WorkspaceReadReceipt` binds run, trace, workspace, fixture, operation, artifact, size, digest,
  returned-byte count, truncation state, policy, provenance, event identity, and UTC observation
  time.

All external service outcomes use existing typed `ControlResult` / `FailureDetail` conventions.
Invalid or unavailable evidence never becomes an ambiguous `None` success.

## W2 proposal contracts and identity

The W2 contracts are deliberately narrower than a general patch format:

- `WorkspaceRemediationKind` has one value: `USE_FIXED_RENDER_START_EXECUTABLE`.
- `WorkspacePatchTarget` fixes the target to `render.yaml` and binds its W1 artifact identity and
  exact before SHA-256.
- `WorkspacePatchChange` fixes the field to `services[0].dockerCommand` and the replacement value
  to `/usr/local/bin/aioa-render-start`; it has no arbitrary content or diff field.
- `WorkspacePatchPreview` contains canonical LF before/after text and a server-rendered unified
  diff. Validation recomputes both content hashes, the transform, and the preview.
- `WorkspaceProposalEvidenceRef` binds exact W1 event, run, trace, workspace, fixture, operation,
  artifact, artifact hash, and canonical receipt hash.
- `WorkspacePatchProposal` binds the base root, target, canonical candidate, patch digest, evidence
  digest, startup script, expected runtime contract, rollback, verification profile, and
  `PLAN_AND_CONFIRM` risk class. Literal false fields deny execution, apply, mutation, process, and
  network authority.

The patch digest hashes a canonical structured payload containing the base/candidate hashes and
closed field replacement. It intentionally excludes UI diff rendering. The proposal digest binds
the complete decision-relevant workspace/evidence/patch content while excluding generated display
text, ID, and timestamps. Re-rendering whitespace cannot change either authority identity.

## Canonical W2 transform

The builder accepts only a sealed `WorkspaceRef`, the closed remediation enum, and server-retained
W1 receipts. It requires an incident inspection, a deployment-log read, and independent hashes of
`render.yaml`, `scripts/render_start.sh`, and `expected_runtime_contract.json`. Cross-workspace,
stale, missing, or changed receipts fail closed.

Trusted code then reads `render.yaml` through the existing descriptor-confined W1 service. The
certified root and three relevant artifact hashes must match the frozen W1 fixture. Exactly one
known folded `dockerCommand` block must exist. The builder replaces only that byte span in memory,
verifies the fixed after line occurs once, computes before/after SHA-256 values, renders stable
`a/render.yaml` / `b/render.yaml` diff headers, and returns the proposal. It has no writable file
handle, apply method, process runner, Git client, package manager, socket, provider, or deployment
adapter.

## Fixture materialization and integrity

`demo/workspace_render_incident_v1` is a public-safe reconstruction of the Render runtime-start
failure. Its timestamps and identifiers are synthetic, and it contains no token, session, personal
data, provider account identifier, host path, or AWS credential. The fixture deliberately provides
evidence for both the primary long-inline-command hypothesis and a token-bootstrap alternative;
the final diagnosis is not stored in a tool or fixture.

For every run, the server:

1. validates the source tree against the exact allowlist;
2. rejects symlinks, special files, multi-link files, unexpected entries, and oversized content;
3. creates a distinct private directory with a UUIDv7 workspace identity;
4. copies content with exclusive creation, flush/fsync, directory mode `0700`, and file mode `0400`;
5. validates the copied artifact set and canonical digest against the source before returning it.

The canonical root digest is derived from fixture/profile identity plus the ordered paths, artifact
types, byte sizes, and content hashes. Host paths, inode numbers, timestamps, and permission bits do
not make the digest machine-specific.

## Workspace jail

The jail treats lexical validation as only the first layer. Accepted artifact names must be
canonical, non-hidden, relative POSIX paths. Absolute paths, dot segments, backslashes, NUL/control
or format characters, overlong segments, and secret-sensitive names are rejected before lookup.
The normalized path must then match the server allowlist.

For each operation the jail also:

- checks exact `WorkspaceRef` equality, preventing cross-run/cross-workspace reads;
- revalidates the root device/inode anchor and the complete fixture digest;
- opens the root, intermediate directories, and file relative to directory descriptors;
- requires `O_NOFOLLOW` and `O_DIRECTORY`, failing closed on unsupported hosts;
- requires a single-link regular file within the server size quota;
- compares device, inode, size, mtime, and ctime before and after the descriptor read;
- independently validates artifact identity and the complete root again after the read;
- maps raw OS errors to stable redacted failures without returning a private host path.

This closes the intended W1 traversal, symlink, special-file, hardlink, cross-workspace, stale-ref,
and fixture-tamper cases. It does not claim containment against a host-privileged attacker.

## Evidence services and tool surface

The evidence service exposes four read operations and records every successful one in a
lock-protected in-memory timeline:

1. `inspect_deployment_incident`
2. `list_workspace_artifacts`
3. `read_workspace_artifact`
4. `hash_workspace_artifact`

List order is canonical and capped. Read validates the full file, returns only a UTF-8 prefix up to
the configured bound, and explicitly reports truncation while retaining the full-file digest. Hash
performs a separate full descriptor read and emits its own receipt. Denials return typed,
non-retryable failure information and do not echo raw exceptions.

W2 adds exactly one composition tool:

5. `build_workspace_patch_proposal`

Its only model-controlled argument is the closed remediation enum. It snapshots retained evidence,
calls the pure builder, and returns exact proposal data.

No write, delete, move, chmod, process, package, Git, browser, MCP, URL, network, or arbitrary host
path operation is registered.

## Strands investigation and proposal profile

`create_workspace_investigation_agent` creates exactly one Strands agent for this runtime profile,
only in portable mock mode with AWS integration disabled. Its `HumanInTheLoop` allowlist is exactly
the four W1 evidence tools plus the inert W2 proposal tool, dynamic directory loading is disabled,
and runtime trace attributes bind profile, run, workspace, authority class, and the
no-network/no-mutation flags.

The system prompt treats artifacts as untrusted data and requires `FACTS`, `AGENT_INFERENCE`,
`SUPPORTING_EVIDENCE`, `EXACT_PATCH_PREVIEW`, `RISK_CLASS`,
`EXPECTED_VERIFICATION_PROFILE`, and `HUMAN_DECISION_REQUIRED`. The model compares the primary and
alternative hypotheses, but only server code constructs the patch. A deterministic mock integration
test exercises the complete evidence/proposal path and proves the answer references observed
artifacts while fixture content stays unchanged.

The canonical CloudOps factory and its five tools remain byte-for-byte unchanged. W1/W2 use their
own explicit factory and do not expand the CloudOps runtime profile.

## Authority classification

| Class | W1/W2 operations |
| --- | --- |
| `AUTO` | inspect sealed metadata; list allowlisted artifacts; bounded read; SHA-256 hash; build inert proposal data |
| `PLAN_AND_CONFIRM` | any future application of the exact proposal; not implemented or authorized in W2 |
| `NEVER_AUTONOMOUS` | arbitrary paths/URLs; network; filesystem mutation; process execution; package install; Git mutation; deployment |

## Threat model and known limits

- The trusted-input boundary is a repository-owned, sanitized fixture. This is not a general
  untrusted checkout sandbox or a replacement for OS/container isolation.
- The descriptor confinement implementation requires Linux/POSIX no-follow directory semantics and
  fails closed if they are absent.
- Receipts are typed and content-bound, but the W1 timeline is process-local and in memory. Durable
  workspace evidence is a future design decision.
- The workspace agent is deliberately portable/mock-only and has no external provider or network path.
- The profile is a library foundation, not a new public HTTP route and not part of the current
  Render startup path.
- W2 can propose only the one frozen structured patch. It cannot apply a patch, mutate a workspace,
  run a process/test, operate Git, install packages, browse, call MCP, access a provider, or deploy.
- Evidence remains in memory. The tracked JSON is a deterministic sanitized demonstration receipt,
  not durable approval and not proof that a patch was applied.

## Frozen deployment boundary

W1 and W2 do not modify repository-root `render.yaml`, `Dockerfile`, `scripts/render_start.sh`,
dependency/lock files, portable startup, deployment secrets, provider resources, AWS state, DNS, or
custom domains. Existing B5/B6 evidence therefore remains valid historical release evidence and is
not regenerated. W3 patch authority is a separate future audit and is not implied by this document.

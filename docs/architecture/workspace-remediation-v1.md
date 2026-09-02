# WORKSPACE_REMEDIATION_V1 architecture

## Status and purpose

Phase W1 provides a sealed, deterministic, read-only workspace for investigating one sanitized
deployment incident. It is an additive runtime profile. It does not migrate or alter the canonical
CloudOps agent, does not apply a patch, and does not expose a general execution platform.

The governing invariant is unchanged:

```text
MODEL_OUTPUT != EXECUTION_AUTHORITY
```

The W1 authority envelope contains only inspect, list, bounded read, and SHA-256 hash operations.
All path scope, identity, quotas, clocks, fixture selection, and policy decisions remain
server-owned.

## Component boundary

```text
trusted sanitized fixture
        |
        v
server materializer -> WorkspaceRef + private immutable copy
        |
        v
WorkspaceJail -> WorkspaceEvidenceService -> four fixed Strands tools -> one W1 agent
        |                    |
        |                    +-> typed result + identity-bound receipt/timeline
        +-> canonical path, inode, type, size, link and digest revalidation
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

The service exposes four operations and records every successful one in a lock-protected in-memory
timeline:

1. `inspect_deployment_incident`
2. `list_workspace_artifacts`
3. `read_workspace_artifact`
4. `hash_workspace_artifact`

List order is canonical and capped. Read validates the full file, returns only a UTF-8 prefix up to
the configured bound, and explicitly reports truncation while retaining the full-file digest. Hash
performs a separate full descriptor read and emits its own receipt. Denials return typed,
non-retryable failure information and do not echo raw exceptions.

No write, delete, move, chmod, process, package, Git, browser, MCP, URL, network, or arbitrary host
path operation is registered.

## Strands investigation profile

`create_workspace_investigation_agent` creates exactly one Strands agent for this runtime profile,
only in portable mock mode with AWS integration disabled. Its `HumanInTheLoop` allowlist is exactly
the four fixed W1 tools, dynamic directory loading is disabled, and runtime trace attributes bind
profile, run, workspace, authority class, and the no-network/no-mutation flags.

The system prompt treats artifacts as untrusted data and requires a diagnosis with `FACTS`,
`AGENT_INFERENCE`, `ALTERNATIVE_HYPOTHESIS`, and `RECOMMENDED_NEXT_STEP`. The tool outputs provide
evidence; the model interprets it. A deterministic mock integration test exercises a seven-turn
tool/reasoning path and proves the answer references observed artifacts while fixture content stays
unchanged.

The canonical CloudOps factory and its five tools remain byte-for-byte unchanged. W1 uses its own
explicit factory and does not expand the CloudOps runtime profile.

## Authority classification

| Class | W1 operations |
| --- | --- |
| `AUTO` | inspect sealed metadata; list allowlisted artifacts; bounded read; SHA-256 hash |
| `PLAN_AND_CONFIRM` | none |
| `NEVER_AUTONOMOUS` | arbitrary paths/URLs; network; filesystem mutation; process execution; package install; Git mutation; deployment |

## Threat model and known limits

- The trusted-input boundary is a repository-owned, sanitized fixture. This is not a general
  untrusted checkout sandbox or a replacement for OS/container isolation.
- The descriptor confinement implementation requires Linux/POSIX no-follow directory semantics and
  fails closed if they are absent.
- Receipts are typed and content-bound, but the W1 timeline is process-local and in memory. Durable
  workspace evidence is a future design decision.
- The W1 agent is deliberately portable/mock-only and has no external provider or network path.
- The profile is a library foundation, not a new public HTTP route and not part of the current
  Render startup path.
- W1 cannot propose a typed patch, mutate a workspace, run tests, operate Git, install packages, or
  deploy. Structured patch proposals belong to a separately reviewed W2 phase.

## Frozen deployment boundary

W1 does not modify `render.yaml`, `Dockerfile`, `scripts/render_start.sh`, deployment secrets,
provider resources, AWS state, DNS, or custom domains. Existing B5/B6 evidence therefore remains
historical release evidence and was not regenerated for this build-only phase.

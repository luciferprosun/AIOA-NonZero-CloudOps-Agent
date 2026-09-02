# W1 heritage-aware sealed workspace foundation — 2026-09-02

## Result

`W1_GATE=PASS` for the certified implementation and tracked fixture at
`0859b5bf8efa62ac9fc4eb8cd2fb8024b39dd5fa` on branch
`codex/w1-heritage-workspace-foundation`.

W1 adds a deterministic sanitized incident fixture, immutable workspace contracts, a server-owned
sealed materializer, a race-conscious read-only jail, typed list/read/hash evidence, and one
four-tool Strands investigation profile. It grants no mutation, process, network, package, Git,
browser, MCP, deployment, or AWS capability.

## Baseline and provenance

| Fact | Verified value |
| --- | --- |
| authoritative base branch | `codex/portable-d1-d2-m1-overnight` |
| base HEAD / remote HEAD | `03d1c8f6a1d254c98c0b4e88fc93e25ea85ed4c7` |
| origin/main observed at start | `4fafed8b1a877e55d96ddd9baea0a737fbeeaa4a` |
| base ahead / behind remote | `0 / 0` |
| certified Render-start checkpoint present | `060ef535fc7bc02ec71c333478333f7340c624e4` |
| deployment-pause handoff present | `03d1c8f6a1d254c98c0b4e88fc93e25ea85ed4c7` |
| historical AOIA-Core inspected read-only | `main` at `20a53ff8872e3aff4b872a021b5a46110549450a` |
| legacy runtime imports added | 0 |

The exact heritage claims, statuses, commit anchors, reuse decisions, and provenance notes are in
`docs/audits/WORKSPACE_REMEDIATION_HERITAGE_MAP_2026-09-02.md`. Historical code was neither copied
wholesale nor imported, vendored, submoduled, or made a runtime dependency.

## Delivered foundation

### Fixed profile and contracts

- Profile `WORKSPACE_REMEDIATION_V1`, version `1`.
- Exact five-artifact server allowlist, `max_files=5`, `max_file_bytes=32768`, and
  `max_read_bytes=4096`.
- Exact operations: `INSPECT`, `LIST`, `READ`, `HASH`.
- Strict `WorkspaceRef`, `WorkspaceArtifactRef`, `WorkspaceObservation`, receipt, policy, and result
  contracts with forbidden extra fields and UUIDv7/SHA-256 validation inherited from Non-Zero.
- `network_allowed=false` and `mutation_allowed=false` are literal contract values, not caller
  options.

### Sanitized real-incident fixture

The five-file fixture reconstructs the known Render exit-127 / `File name too long` event using
synthetic timestamps and identifiers. Its canonical artifact-set digest is
`84172797b4203b01e7404649449ac7b6468e94b88e7aba9b2104d18c01668db8`.
It contains no real token, cookie, nonce, email, account metadata, host path, AWS credential, or ARN.

### Jail and evidence plane

- Every materialization receives a distinct server-generated UUIDv7 workspace identity and private
  root.
- Source and copied trees are exact-allowlist, regular-file, single-link, quota, and digest checked.
- Path contracts reject traversal, absolute paths, non-POSIX separators, hidden/sensitive names,
  and NUL/control/format characters.
- Reads use root-relative directory descriptors with no-follow semantics and before/after inode /
  metadata checks, followed by full-root digest revalidation.
- Cross-workspace, stale artifact, missing, unexpected, symlink, hardlink, special-file, oversized,
  replaced-root, and tamper cases fail closed with typed redacted results.
- Successful inspect/list/read/hash events bind event, run, trace, workspace, fixture, artifact,
  operation, size, digest, policy, provenance, and UTC timestamp.
- Bounded reads report returned bytes and explicit truncation while retaining the full-file digest;
  hash is an independent read receipt.

### Read-only Strands profile

The additive profile creates exactly one agent with exactly these tools:

1. `inspect_deployment_incident`
2. `list_workspace_artifacts`
3. `read_workspace_artifact`
4. `hash_workspace_artifact`

It accepts only portable mock runtime settings with AWS disabled. The test model selects and calls
the evidence tools, compares a primary and alternate hypothesis, cites artifact paths, and returns a
structured diagnosis. The diagnosis is not embedded in the fixture or tool output.

The existing CloudOps `create_primary_agent`, five-tool tuple, HITL/replay/recovery flows, provider
boundary, and deployment startup contract were not modified.

## Adversarial coverage

The explicit W1 suite contains 50 passing cases across
`tests/unit/test_workspace_foundation.py` and
`tests/integration/test_workspace_strands_profile.py`.

| Required boundary | Result |
| --- | --- |
| unique workspace identity and deterministic digest | PASS |
| traversal / absolute / NUL / control / non-POSIX rejection | PASS |
| symlink, FIFO/socket/device, and multi-link rejection | PASS |
| cross-workspace and unknown artifact denial | PASS |
| hidden / secret-sensitive path denial | PASS |
| server-owned quotas and explicit truncation | PASS |
| deterministic capped list and independent read/hash digests | PASS |
| root, artifact, and extra-file tamper detection | PASS |
| read creates or modifies no file | PASS |
| zero mutation and zero network profile capability | PASS |
| exact one-agent/four-tool surface and unknown-tool denial | PASS |
| fixture secret scan | PASS |
| concurrent identity isolation and redacted host errors | PASS |
| provenance timeline and evidence-referencing agent diagnosis | PASS |

## Certification results

| Gate | Result | Detail |
| --- | --- | --- |
| full pytest | PASS | 1515/1515 in 785.50 s |
| explicit W1 tests | PASS | 50/50 in 5.16 s |
| P0 | PASS | 15/15 gates; 136 proofs; 0 skipped |
| P1 | PASS | 6/6 gates; 93 proofs; 0 skipped |
| B4 | PASS | 11/11 scenarios; 43 proofs; 0 skipped |
| Ruff | PASS | all repository checks |
| pip check | PASS | no broken requirements |
| git diff --check | PASS | no whitespace errors |
| canonical secret scan | PASS | 438 files; 0 findings; 0 values emitted |
| local clean clone | PASS | tracked five-file fixture; W1 50/50; secret scan 438/0 |
| external egress during certification | PASS | 0 |
| AWS calls / mutations | PASS | 0 / 0 |

B4 independently reported loopback-only fail-closed networking, zero external network calls, zero
AWS calls, zero AWS mutations, and zero deployments.

## Frozen compatibility evidence

The following SHA-256 values match the selected base exactly:

| Frozen input | SHA-256 |
| --- | --- |
| `render.yaml` | `c9e351188844ec4236068ffe62fa9747376ec520eabea39c9e92dd30909a645c` |
| `Dockerfile` | `4640463904ced78776f5f482510e9f117d7ee2e0b6a8e04c5ba83e349378bc8f` |
| `scripts/render_start.sh` | `d350917c132a338605f630fde97a2ac017e1664fe9cf413a7153827326e6d250` |
| CloudOps `agent/factory.py` | `4f1b02661a1effab421b3ec6ed506bf50a97c17ca5eb66cf959d201e0a881822` |
| `pyproject.toml` | `c11d0b6bc5a804599ecebed13753b16918d13d990735ab764cd9e000c08cfc5a` |

There is no dependency/lock-file change. B5/B6 recertification is intentionally out of scope because
none of their frozen Docker/Render/startup inputs changed; their historical PASS evidence was not
rewritten.

## Regression investigation record

The first full suite exposed two compatibility assumptions rather than runtime defects:

1. A serialized artifact type value `SHELL` used the same Python member identifier and triggered a
   conservative AST name check. The identifier is now `SHELL_SCRIPT` while its public serialized
   value remains `SHELL`; no process capability exists.
2. The historical P0 runner counts the canonical CloudOps `Agent` constructor and is itself a
   hash-bound reviewer authority source. A temporary attempted runner update in `ec05c7f` correctly
   triggered reviewer-evidence drift. Commit `a0e30a4` restores the runner byte-for-byte and keeps
   the additive constructor explicit as `StrandsAgent`; the separate W1 integration suite proves
   exactly one agent and four tools for the workspace profile. The reviewer manifest, P0, and P1
   all pass without changing historical evidence.

The final full suite passed 1515/1515 after these corrections.

## Known limitations and safe next step

- W1 trusts a repository-owned sanitized fixture and does not claim a host-privileged sandbox.
- Descriptor confinement requires POSIX `O_NOFOLLOW` / `O_DIRECTORY` support and fails closed when
  unavailable.
- The evidence timeline is in memory; no new durable workspace store is introduced.
- The agent profile is mock-only and is not wired to the public Render service or a new HTTP route.
- No patch proposal or application, arbitrary workspace, process runner, test runner, Git operation,
  dependency installation, browser/MCP adapter, or deployment exists in W1.

The next safe step is a separately audited W2 design for a structured, non-applying patch proposal.
W2 must not be inferred as authorization to mutate files, run commands, deploy, or access providers.

## Commit sequence

1. `4d7493c` — `docs(audit): map reusable AOIA heritage capabilities`
2. `f4c9cf7` — `feat(workspace): add sealed workspace contracts and fixture`
3. `b8745b5` — `feat(workspace): enforce jailed read-list-hash evidence plane`
4. `8d2af3f` — `feat(agent): add read-only workspace investigation profile`
5. `ecc6cf6` — `test(workspace): certify W1 path and evidence boundaries`
6. `ec05c7f` — `test(gates): certify isolated workspace agent topology`
7. `a0e30a4` — `fix(workspace): preserve frozen P0 authority evidence`
8. `dc38e7b` — `docs(workspace): freeze W1 foundation checkpoint`
9. `0859b5b` — `fix(fixture): track sanitized deployment evidence`
10. The commit containing this reconciliation —
    `docs(workspace): certify clean-clone fixture checkpoint`

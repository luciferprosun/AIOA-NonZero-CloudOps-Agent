# W2 structured non-applying patch proposal — 2026-09-03

## Result

`W2_GATE=PASS` for the implementation and deterministic evidence at
`65e468e8d37061aaacb0b8a48d206ac773c78024` on branch
`codex/w2-structured-patch-proposal`, subject to the final documentation commit and remote-ref
verification recorded at handoff.

W2 converts the W1 evidence-backed Render startup diagnosis into one exact, content-addressed,
server-generated proposal. No patch was applied, no approval was requested or consumed, no process
was executed from the workspace, and no workspace file was created, deleted, or modified. W2 does
not authorize or implement W3/W4.

```text
MODEL_OUTPUT != EXECUTION_AUTHORITY
PATCH_PROPOSAL != PATCH_AUTHORITY
PATCH_PREVIEW != FILE_MUTATION
ACTION_ACKNOWLEDGEMENT != SUCCESS
```

## Certified base

| Fact | Verified value |
| --- | --- |
| required base branch | `codex/w1-heritage-workspace-foundation` |
| local/remote W1 HEAD | `772eda44a1c84581d7d63f8f8848b4440598fe0c` |
| W1 implementation anchor | `0859b5bf8efa62ac9fc4eb8cd2fb8024b39dd5fa` |
| W1 ahead / behind before branch | `0 / 0` |
| W1 audit gate | PASS |
| W1 reported full baseline | 1515/1515 |
| W1 explicit suite re-run | 50/50 |
| W1 P0 / P1 / B4 | 15/15, 6/6, 11/11 |

Origin was fetched before branching. The feature branch was created from the exact certified W1
remote HEAD, not from `main` or the deployment branch.

## Closed proposal contract

The model may select only
`WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE`. The proposal tool accepts no target
path, replacement document, unified diff, shell command, argv, URL, or provider identifier.
Server code owns the only transform:

```text
target: render.yaml
field:  services[0].dockerCommand
before: exact certified long folded inline bootstrap block
after:  /usr/local/bin/aioa-render-start
```

The proposal binds UUIDv7 proposal/run/trace/workspace identities, fixture version, base root,
target before hash, candidate after hash, structured patch digest, exact W1 receipt hashes,
evidence digest, supporting startup-script hash, expected-runtime-contract hash, rollback strategy,
verification profile, expiry/version, and `PLAN_AND_CONFIRM` future-apply risk.

Literal contract fields remain:

- `authorizes_execution=false`
- `apply_authority_granted=false`
- `mutation_allowed=false`
- `process_execution_allowed=false`
- `network_allowed=false`

## Canonical identity

| Identity | SHA-256 |
| --- | --- |
| certified W1 fixture root | `84172797b4203b01e7404649449ac7b6468e94b88e7aba9b2104d18c01668db8` |
| `render.yaml` before | `b957bbf10af3d711fbfeda271f8ba3b362894f4b02bb8d88239985769a3968db` |
| canonical candidate after | `91eb20346909ca23779cdaf773586a9a925ebf59e90113615ecedcd24dc05314` |
| structured patch digest | `73be5422645433ca51371ab992854e028149c9a06753b61e1d66bfe5ed0ee5f0` |
| evidence digest | `4de8a59272f4f9cf57e2ad3c679897c2a9610d3fef858d0139268bb852ff6675` |
| deterministic demo proposal digest | `c9d9537e49e8388ba2ca5b92538383ca8c69d0d7fd2f704d2240002414736499` |
| supporting startup script | `d350917c132a338605f630fde97a2ac017e1664fe9cf413a7153827326e6d250` |
| expected runtime contract | `8bf5a36539ea313a578e194e1c84568586770cc792d60709ebde106df9325178` |

The patch digest comes from canonical structured JSON, not from the displayed unified diff. The
contract separately recomputes and validates the exact LF before/after content and deterministic
`a/render.yaml` / `b/render.yaml` diff. UI whitespace therefore cannot alter proposal identity.

The complete strict, reproducible JSON receipt is
`docs/evidence/workspace/w2-patch-proposal.json`.

## Evidence and drift boundary

Proposal construction requires exact retained W1 evidence for:

1. incident inspection and sealed root identity;
2. `deployment.log` read receipt;
3. independent `render.yaml` hash receipt;
4. independent `scripts/render_start.sh` hash receipt;
5. independent `expected_runtime_contract.json` hash receipt.

The builder rejects cross-workspace evidence, unretained/stale receipts, base-root drift, target
drift, supporting-artifact drift, incomplete evidence, unsupported remediation, ambiguous or
duplicate `dockerCommand` targets, noncanonical previews, unrelated candidate changes, and unknown
contract fields. Failures use the closed W2 outcome taxonomy and redact private host details.

## Exact tool surface

The separate `WORKSPACE_REMEDIATION_V1` profile has one agent and exactly five tools:

1. `inspect_deployment_incident`
2. `list_workspace_artifacts`
3. `read_workspace_artifact`
4. `hash_workspace_artifact`
5. `build_workspace_patch_proposal`

The fifth tool snapshots retained evidence and calls the pure builder. Its schema contains only
`remediation_kind`, and its description states that it performs no filesystem mutation and grants
no execution authority. The canonical CloudOps five-tool surface and factory remain unchanged.

## No-effect and capability proof

| Boundary | Result |
| --- | --- |
| workspace files created | 0 |
| workspace files deleted | 0 |
| workspace files modified | 0 |
| sealed workspace mutation delta | 0 |
| process execution capabilities registered | 0 |
| network capabilities registered | 0 |
| package-install capabilities registered | 0 |
| Git mutation capabilities registered | 0 |
| browser/MCP capabilities registered | 0 |
| AWS calls / mutations during B4 | 0 / 0 |
| external network calls during B4 | 0 |
| external deployments during B4 | 0 |
| Render actions | 0 |
| paid resources created | 0 |

The no-effect test snapshots type, mode, size, mtime, and content digest for the complete sealed
tree before and after the successful proposal flow. It proves exact equality. Engineering test
processes are certification activity; no process-execution capability exists in, or is invoked by,
the workspace proposal flow.

## Certification

| Gate | Result | Detail |
| --- | --- | --- |
| explicit W2 tests | PASS | 34/34 |
| explicit W1 tests | PASS | 50/50 |
| full pytest | PASS | 1549/1549 in 638.90 s |
| P0 | PASS | 15/15 gates; 136 proofs; 0 skipped |
| P1 | PASS | 6/6 gates; 93 proofs; 0 skipped |
| B4 | PASS | 11/11 scenarios; 43 proofs; 0 skipped |
| local clean clone | PASS | W1+W2 84/84; secret-scan receipt identical |
| Ruff | PASS | full repository |
| pip check | PASS | no broken requirements |
| git diff check | PASS | no whitespace errors |
| canonical secret scan | PASS | 443 files; 0 findings; 0 values emitted |

The full test delta from W1 is exactly the 34 focused W2 tests: 1515 + 34 = 1549.

## Frozen deployment and compatibility evidence

No B5/B6 full recertification is required because all publication/runtime-bound inputs remain
unchanged from W1:

| Frozen input | SHA-256 |
| --- | --- |
| repository-root `render.yaml` | `c9e351188844ec4236068ffe62fa9747376ec520eabea39c9e92dd30909a645c` |
| `Dockerfile` | `4640463904ced78776f5f482510e9f117d7ee2e0b6a8e04c5ba83e349378bc8f` |
| `scripts/render_start.sh` | `d350917c132a338605f630fde97a2ac017e1664fe9cf413a7153827326e6d250` |
| `pyproject.toml` | `c11d0b6bc5a804599ecebed13753b16918d13d990735ab764cd9e000c08cfc5a` |
| CloudOps `agent/factory.py` | `4f1b02661a1effab421b3ec6ed506bf50a97c17ca5eb66cf959d201e0a881822` |
| `requirements/build.lock` | `d46492123b794c100b45c485f2981c1a12f71388f61439a5a662d850b19039a5` |
| `requirements/portable.lock` | `a7be92862cb66b67f2bf5b664f62abee1dbd48d65e2ee12fbcbaa5be2dff5dcd` |

`git diff` from the exact W1 base reports no change under these deployment/runtime inputs. The
existing CloudOps, HITL, replay, recovery, provider, portable-server, and Render startup paths pass
the full regression and all historical gates.

## Commit sequence

1. `1133c63` — `feat(workspace): add inert structured remediation proposal contracts`
2. `31cfb95` — `feat(workspace): generate deterministic proof-carrying patch preview`
3. `0863675` — `feat(agent): expose non-applying patch proposal tool`
4. `65e468e` — `test(workspace): certify W2 proposal binding and zero-effect boundary`
5. final documentation checkpoint — `docs(workspace): freeze W2 structured proposal checkpoint`

## Known limitations and next safe step

- The profile remains portable/mock-only and operates on the repository-owned sanitized fixture.
- The evidence timeline is process-local; the tracked receipt is sanitized demonstration evidence,
  not approval or execution truth.
- Only one exact v1 Render remediation is supported.
- W2 has no apply/write/delete/process/test/Git/package/browser/MCP/provider/deployment authority.
- A proposal expiry does not create an approval and cannot be consumed by W2.

The next safe step is a separately audited W3 design for human-bound exact patch authority.
`READY_FOR_W3_HUMAN_BOUND_PATCH_AUTHORITY=YES` means the W2 prerequisite is certified; it is not
authorization to implement W3, apply this patch, consume approval, run workspace commands, or
deploy.

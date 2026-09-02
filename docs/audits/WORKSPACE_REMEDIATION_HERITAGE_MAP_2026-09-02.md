# Workspace remediation heritage map — 2026-09-02

## Scope and provenance

This audit maps reusable design evidence for
`WORKSPACE_REMEDIATION_V1`. The current hackathon repository remains the only implementation
authority. Historical AOIA material was inspected read-only and is not a runtime dependency.

- Authoritative AIOA base: `codex/portable-d1-d2-m1-overnight` at
  `03d1c8f6a1d254c98c0b4e88fc93e25ea85ed4c7`.
- Historical source: `https://github.com/luciferprosun/AOIA-Core.git`, `main` at
  `20a53ff8872e3aff4b872a021b5a46110549450a` plus the exact historical commits cited below.
- Inspection date: 2026-09-02.
- Both repositories carry MIT licenses. This phase reimplements small concepts and test ideas in
  the current package; it does not copy historical modules.
- `NO_LEGACY_CODE_IMPORT=TRUE` remains binding under `docs/DECISIONS.md` D-002.

## Mandatory capability matrix

| Historical capability / idea | Verified artifact | Status | Reuse mode | W1 relevance |
| --- | --- | --- | --- | --- |
| Controlled Git / push concepts | AOIA-Core `runtime/git_ops/git_controlled_push.py` and `tests/test_controlled_git_push_1a.py` at `eccbcd912c050ad8bfe36cc7dba1c8a3d4312243`; fail-closed edge tests at `f8fc328fe59e19afc627423acba71f772c14081b` | Implemented on historical non-main development lineage; not adopted by AIOA | Design/test only: exact refs, clean-tree checks, hash-bound previews, TOCTOU revalidation and fail-closed reason codes; no W1 Git API or remote mutation | Future Git evidence only; explicitly absent from W1 tool surface |
| Structured clone / taxonomy | AOIA-Core `scripts/dev/create_ioa_lab_clone.py` and `docs/audit/DEV_TOOLS_2_IOA_LAB_CLONE_REPORT.md` at `36889c238a21289f4fdefc79914887f519ca38c1`; `docs/TAXONOMY_NORMALIZATION_REPORT.md` and `MHLM_MHSR/framework/taxonomy/case_studies.yml` at `784240aa55fd13a16a30a76a38b952efdaa9c0f8` | Implemented historical local-clone utility plus archived/current taxonomy documentation | Reuse isolation and classification ideas only: server-owned root, disabled remote, canonical labels, preserved historical names; no utility copy | Sealed fixture/workspace identity and explicit fixture provenance |
| Critic / adversarial corpus | AOIA-Core `runtime/providers/critic_taxonomy.py` at `651c51f819e85d9d558b0d55b06d6826b2782344`; `runtime/providers/critic_adversarial_corpus.py` and `tests/test_critic_adversarial_corpus_1a.py` at `1279a5aa1ee3bf52a28f52ebb188b88def42e058`; main `MHLM_MHSR/case_studies/anti_hallucination_epi_app/contradictions/CONTRADICTION_TAXONOMY.md` at `784240aa55fd13a16a30a76a38b952efdaa9c0f8` | Implemented on historical development lineage; contradiction document is taxonomy-only | Reuse attack cases and failure classes: authority smuggling, path sandbox, TOCTOU, evidence/hash mismatch, provider fallback and unknown capability | Drives W1 negative path, cross-workspace, tamper and unavailable-state tests |
| Provider gateway / model boundary | Current AIOA `src/aioa_cloudops_agent/providers/factory.py` at `a2e16d0f1d625b34916440d6740a486f73cf2bb1`; AOIA-Core `runtime/providers/base.py` at `1861e94a42afea68d8a569460e8873adaddf445b` | Current provider factory implemented and authoritative; historical adapter archived | Reuse current explicit-provider/no-silent-fallback boundary. Historical fallback implementation is evidence of a risk, not code to revive | One explicit Strands profile and portable deterministic provider discipline |
| Schema validation / contracts | Current AIOA `src/aioa_cloudops_agent/nz/contracts.py`, `nz/errors.py`, and `nz/identifiers.py` at base `03d1c8f6a1d254c98c0b4e88fc93e25ea85ed4c7`; AOIA-Core `runtime/knowledge/schema/command.schema.json` at `1861e94a42afea68d8a569460e8873adaddf445b` | Implemented in current repository; historical JSON Schema implemented for a different domain | Reuse current frozen Pydantic contract pattern, discriminated results, canonical SHA-256 and extra-field denial; reimplement workspace-specific types | `WorkspaceRef`, artifact refs, policy decisions, observations and read/hash receipts |
| Runner payload expansion | AOIA-Core `runtime/providers/provider_payload_governance.py` at `c9cdc2bb6038b5fd673b500cd639b583cd1d7bc7`; `runtime/safety/sandbox_workspace.py`, `runtime/safety/sandbox_artifact_runner.py`, and `runtime/schemas/sandbox_artifact.py` at `3ee708a61d225f2ae07130fb9a25c81a39517e5d` | Implemented on historical development lineage; includes mutation behavior outside W1 scope | Reuse bounded payload, digest, provenance, path-confinement and typed-denial lessons only. Do not copy write runner or authority flags | Read/list/hash receipts now; future verification profiles only |
| Package manager / install | AOIA-Core `runtime/package_ops/package_install_proposal.py` at `dff45c6af7acea63f6dda9b681be8091c3295c80` and `runtime/package_ops/controlled_package_install.py` plus tests at `5ed23979f4733f2cc9ad30e34b91dd7b8eebdc29` | Implemented on historical development lineage; not approved for current runtime | DEFER. Retain lessons about exact package identity, pinning, stale evidence, human boundary and supply-chain scope for a post-hackathon Linux pack | Not implemented; zero package-install capability in W1 |
| Browser / device automation | AOIA-Core `runtime/browser_ops/controlled_browser_read.py` at `0d1a23384841ba51199212c31385a7ecedd48f75`, `runtime/browser_ops/browser_automation_governance.py` at `d13c276751b4f2005ba83fabbbd8f72d5b7a727e`, and controlled automation at `9fe25e72d25b34bb4e3bbc3141b465dfdb5c99bc`; device-specific automation artifact: **NOT FOUND** | Browser path implemented on historical development lineage; device automation not found | DEFER/CUT. Retain distinction between read and effect, exact action allowlists, navigation/form/download denial and evidence binding | Not implemented; zero browser/device capability in W1 |
| MCP | AOIA-Core `runtime/integration_boundaries/mcp_boundary.py` and `tests/test_mcp_boundary_1a.py` at `d1b8839f4251bf4030b63700337c15667b842b03` | Implemented as historical metadata-only boundary; no W1 connector runtime | Future adapter only. Reuse explicit transport/capability classification and the rule that declarations/proposals confer no authority | Not implemented; zero MCP transport, tool call or resource read in W1 |
| Async I/O | AOIA-Core `runtime/orchestration/async_io_orchestration.py` and `tests/test_async_io_orchestration_1a.py` at `44f2e741fd61b2e1d64c18d2c00d9eea5454e2d0` | Implemented as inert metadata orchestration on historical lineage | Reuse only deterministic dependency ordering, bounded operation counts, `retry=none` and cycle/unknown dependency rejection if a current contract later needs them | No W1 architecture expansion; concurrent reads remain ordinary isolated service calls |
| Local agent loop / prompt loop | AOIA-Core `runtime/agent_loops/local_agent_loop.py` at `76112f9aa104e49cc6b3f914595658f758af344a` and `runtime/agent_loops/provider_agent_loop.py` at `62107bc6f78e4861d2c7d151f167c726ab22d9c8`; current AIOA `src/aioa_cloudops_agent/agent/factory.py` at base `03d1c8f6a1d254c98c0b4e88fc93e25ea85ed4c7` | Historical bounded loops implemented off main; current single Strands factory implemented and authoritative | Reuse current exactly-one-agent construction. Reuse only historical objective/evidence binding and forbidden-action vocabulary; no nested/provider loop execution | Add one read-only workspace investigation profile with four fixed tools |

All commit identifiers above are full object IDs from the inspected repositories.

## Reuse decisions for W1

The following concepts are selected for clean-room reimplementation:

1. Server-owned workspace root, identity, allowlist and quotas.
2. Strict immutable contracts with unknown fields forbidden.
3. Canonical digests over deterministic fixture content and every allowed artifact.
4. Explicit typed success/failure and stable fail-closed reason codes.
5. Revalidation at operation time for path, type, size, digest and workspace identity.
6. Evidence that binds run, trace, workspace, fixture, artifact, operation and timestamp.
7. A fixed, additive, exactly-four-tool Strands surface whose tool output is evidence rather than
   authority.

The following historical designs are explicitly rejected for W1:

- generic execution or filesystem registries;
- shell, subprocess, Git, package, browser, MCP or network adapters;
- provider fallback chains and ambient secret discovery;
- writable sandbox artifact runners;
- dynamic capability discovery;
- model-controlled roots, paths, quotas, clocks or identity;
- historical runtime imports, submodules, copied modules or hidden AOIA-Core dependencies.

## Boundary conclusion

`HERITAGE_REUSE_MAP=COMPLETE` and `NO_LEGACY_CODE_IMPORT=TRUE`. Historical evidence materially
reduces redesign risk, but current AIOA Non-Zero contracts remain authoritative. The W1
implementation must be newly authored, read-only, dependency-neutral, and independently tested.

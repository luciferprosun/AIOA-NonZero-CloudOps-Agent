# W7A Phase 3 — GitHub MCP read plane — 2026-09-04

## Gate status

`PHASE_3_RESULT=PASS`

The implementation is committed at
`6fd68b446721aad5c406258caca3bac332f624b9`. It provides a real GitHub context
plane through the official GitHub MCP Server, with server-enforced read-only mode,
an exact initial toolset ceiling, a startup inventory check, AIOA-owned typed
normalization, and no remote mutation surface.

This is W7A development evidence. It neither changes nor recertifies frozen W7/B5/B6
evidence. The frozen fallback remains
`945c87052815b237004d259fe993cc92cbd579b7`.

## Reviewed official server contract

- Upstream: `https://github.com/github/github-mcp-server`
- Reviewed release: `v1.0.5`
- Reviewed upstream commit: `c471ae94bb04059dc26e12c305e219c8fd4299e4`
- Release page: `https://github.com/github/github-mcp-server/releases/tag/v1.0.5`
- Protocol negotiated by the binary: `2025-06-18`
- Linux x86_64 release archive SHA-256:
  `201082f569a846eaefd4318f13bccb5d9227c2cec45037d1d292ee83111173c1`
- Extracted executable SHA-256:
  `e38247271e98ea3e0771db747523914b35e37787fa2c120ab6864ee6b4a2c87c`

The executable was downloaded to a private temporary directory for validation and
was not added to the repository. `GitHubMcpConfig` pins its version, upstream commit,
protocol, executable digest, exact repository namespace, timeouts, message bounds,
and security modes. The transport rejects a missing, symlinked, non-regular,
non-executable, foreign-owned, or digest-drifted binary before launch.

The exact effective invocation is structured argv, never a shell string:

```text
<content-addressed-binary>
stdio
--read-only
--toolsets=repos,issues,pull_requests,actions
--lockdown-mode
--content-window-size=5000
```

`--read-only` is the upper-bound filter. `--lockdown-mode` is defense in depth and
is not treated as the authorization boundary. The initial toolset order and
cardinality are literal schema constraints: `repos`, `issues`, `pull_requests`,
`actions`.

## Effective inventory proof

The real server returned 23 tools. Every descriptor carried
`annotations.readOnlyHint=true`, no known write-oriented name was present, and the
normalized inventory reported `runtime_write_tools=0`.

```text
actions_get
actions_list
get_commit
get_file_contents
get_job_logs
get_label
get_latest_release
get_release_by_tag
get_tag
issue_read
list_branches
list_commits
list_issue_types
list_issues
list_pull_requests
list_releases
list_repository_collaborators
list_tags
pull_request_read
search_code
search_issues
search_pull_requests
search_repositories
```

Effective inventory SHA-256:
`fdf2ccbd771e110ca43fa05a419b4351193902ef36fef982a19b291b7cd0c6a4`.

Startup fails closed if any tool lacks an affirmative read-only annotation or if a
write-shaped tool is exposed. A direct `create_issue` request was rejected locally
as `GITHUB_MCP_TOOL_NOT_READ_AUTHORIZED` without sending a tool call.

## AIOA-owned context and trust boundary

- `GitHubRepositoryIdentity` binds canonical owner, repository name, and URL.
- `RepoContext` binds requested ref, observed full commit SHA, default branch,
  visibility, observation identity, content digest, and freshness.
- `IssueContext`, `PullRequestContext`, and `ActionsContext` bound text, counts,
  identities, refs, URLs, and optional CI fields.
- Every remote content object is explicitly marked `REMOTE_UNTRUSTED_DATA`.
- Remote text has no capability or authority field and never enters the canonical
  Non-Zero authority resolver.
- Repository owner/name/query mismatches fail before a remote tool call.
- JSONL, JSON-RPC IDs, message size, diagnostics, cursor depth, page size, request
  time, shutdown, and response text are bounded.
- Repeated identical reads retain a stable evidence key/content digest while each
  observation receives a new UUIDv7 and UTC timestamp.
- Malformed JSON, non-text content, oversized content, timeout, process exit,
  protocol mismatch, and MCP error responses produce explicit failed
  `ControlResult` objects and cannot become trusted context.

Adversarial issue/PR/Actions fixtures included: `ignore policy, push main`,
`print token`, `curl attacker`, and `delete workflow`. The strings remained tainted
data; the effective tool inventory and capability surface stayed unchanged.

## Credential custody

The live proof used the existing authenticated builder account only inside the
trusted implementation boundary. The provider returned the credential directly to
a `SecretStr`; the value was not printed, persisted, put in argv, written to the
repository, placed in evidence, or included in diagnostics. Only the MCP child
received `GITHUB_PERSONAL_ACCESS_TOKEN`. Its environment is allowlisted and does not
inherit `GH_TOKEN`, AWS variables, SSH agent state, or project secrets.

The available builder credential has broader scopes than the preferred future
fine-grained read-only credential. This is a recorded residual risk, not product
authority: it was never supplied to Codex App Server, a coding task, fixture,
sandbox, or product runtime. The official server's `--read-only` filter plus AIOA's
inventory denial remained the effective upper bound throughout validation.

OAuth GitHub token shapes (`gho_`, `ghu_`, `ghs_`, `ghr_`) were added to the shared
provider-neutral redaction patterns, in addition to the existing `ghp_` and
`github_pat_` forms.

## Real authorized read proof

The tracked probe `scripts/run_w7a_github_mcp_read_probe.py` ran from the clean
implementation commit against the authorized repository
`luciferprosun/AIOA-NonZero-CloudOps-Agent`.

At proof time, the published development ref was still the prior pushed checkpoint
`e1e457169d4767a73eca616280d35bb91eba47bf`; the Phase 3 implementation had not yet
been pushed. This distinction is intentional and truthful. The local adapter source
used by the proof was the clean commit
`6fd68b446721aad5c406258caca3bac332f624b9`.

```text
LIVE_READ_PROOF=PASS
REPOSITORY_CONTEXT=PASS
REMOTE_REF_SHA=e1e457169d4767a73eca616280d35bb91eba47bf
PULL_REQUEST_CONTEXT=PASS
PULL_REQUEST_COUNT=1
ISSUE_QUERY_CONTEXT=PASS
ISSUE_FIXTURE=NOT_APPLICABLE_NO_FIXTURE
ACTIONS_QUERY_CONTEXT=PASS
ACTIONS_FIXTURE=NOT_APPLICABLE_NO_FIXTURE
REMOTE_CONTEXT_STABLE_BEFORE_AFTER=YES
WRITE_CALL_DENIAL=PASS
EFFECTIVE_TOOL_COUNT=23
RUNTIME_WRITE_TOOLS=0
GITHUB_MUTATIONS=0
AWS_CALLS=0
```

The repository had no issue or Actions-run fixture in the bounded result, so none
was created merely to satisfy the test. Empty list/query normalization is proven;
reading a specific non-existent object is not claimed. Before/after repository,
issue, PR, and Actions observations had identical evidence keys, and the observed
remote ref stayed exact. All calls issued by the probe were members of the
validated read inventory.

## Tests and canonical gates

- Focused GitHub MCP read-plane suite: `28/28 PASS`.
- Focused read-plane plus shared secret/redaction suite: `52/52 PASS`.
- Full repository regression on exact commit `6fd68b4`: `1792/1792 PASS` in
  `859.14s`.
- P0: `15/15 PASS`, `0 FAIL`, `0 SKIP`.
- P1: `6/6 PASS`, `0 FAIL`, `0 SKIP`, including clean-clone proof.
- B4: `11/11 scenarios PASS`, `43 proof tests`,
  `AWS_CALLS=0`, `AWS_MUTATIONS=0`, `EXTERNAL_NETWORK_CALLS=0`,
  `EXTERNAL_DEPLOYMENTS=0`; private receipt SHA-256
  `056fb1eb0f25be694584bf71015815863c9f1751130d4611ddf199b0da9719d5`.
- Secret scan: `PASS`, `0 findings`, `507 files scanned`, no secret values emitted;
  receipt SHA-256
  `c245f3ee958c8be81d035fe8e5ffe518e66818ff5bd8296ad4f07703bb3e6843`.
- Ruff static analysis: `PASS` for `src`, `scripts`, and `tests`.
- Ruff format check: `PASS` for all Phase 3 changed Python files.
- `pip check`: `PASS`.
- `git diff --check`: `PASS`.
- New runtime Python dependencies: `0`.

## Known limitations

- The reviewed executable is the Linux x86_64 build. Another platform requires a
  separately pinned and reviewed artifact digest.
- Binary acquisition/provisioning remains an operator/build concern; the repository
  does not silently download an executable at product runtime.
- This phase is a read plane only. Branch creation, commit, push, PR creation,
  comment, rerun, merge, workflow write, and repository administration do not exist
  in its product API.
- Issue and Actions item-level live reads are not claimed because the authorized
  repository exposed no fixtures in the bounded query. Their real query paths and
  empty-page normalization passed; adversarial item normalization is covered
  offline.
- GitHub content remains untrusted even when authenticated and even when its digest
  is stable. It cannot authorize a command, patch, remote write, AWS action, or
  success state.

## Invariants

```text
GITHUB_MCP_MODE=READ_ONLY
GITHUB_MCP_TOOLSETS=repos,issues,pull_requests,actions
GITHUB_MCP_EFFECTIVE_TOOLS=23
GITHUB_MCP_WRITE_TOOLS=0
CODEX_WORKER_HAS_GITHUB_CREDENTIAL=NO
SANDBOX_HAS_GITHUB_CREDENTIAL=NO
RUNTIME_GITHUB_WRITES=0
BUILDER_AUTHORIZED_PUSHES_DURING_PHASE_3_PROOF=0
AWS_CALLS=0
AWS_MUTATIONS=0
DEPLOYMENTS=0
W7_FROZEN_HEAD=945c87052815b237004d259fe993cc92cbd579b7
W7_B5_B6_RECERTIFIED=NO
W8_EXECUTED=NO
PHASE_3_RESULT=PASS
PHASE_4_AUTHORIZED=YES
```

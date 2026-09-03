# W6 feature freeze

Feature additions stop at the W6 security checkpoint. W7 and W8 may harden, package, certify and
document the frozen product, but may not introduce a new runtime capability or broaden authority.

## Keep/cut decision

| Visible W1-W5 feature | Decision | Reason and submission boundary |
| --- | --- | --- |
| W1 sealed incident workspace and bounded evidence reads | KEEP | Deterministic, judge-visible evidence with no mutation/process/network capability |
| W1 five-tool offline investigation profile | KEEP | Closed mock-only tool surface; clear evidence-gathering value |
| W2 exact content-addressed patch proposal and unified diff | KEEP | Proposal is inert, exact and explainable; it grants no authority |
| W3 durable human approval card and exact actor/nonce decision | KEEP | Core Agents for Humans value; approval remains separate from execution |
| W3 proposal-ID-only atomic apply | KEEP | One exact private-workspace file effect with at-most-once ownership |
| W4 independent fixed-profile verifier | KEEP | Required separation between executor acknowledgement and truth |
| W4 recovery/reconciliation and replay rejection | KEEP | Demonstrates crash safety and no duplicate semantic effect |
| W5 fixed failed-deployment hero scenario | KEEP | Complete story can be explained and demonstrated in under five minutes |
| W5 approve, deny, refresh and replay UI controls | KEEP | Deterministic, bounded and directly useful to judges |
| Existing CloudOps deterministic judge scenarios | KEEP | Backward-compatible regression surface; clearly labelled mock/deterministic |
| Local loopback/API demo and container startup contract | KEEP | Reproducible without AWS credentials; public bind remains deployment-controlled |
| Optional Bedrock/AWS adapters already present | DISABLE FROM CORE PATH | Retained as optional code, but no live-AWS claim or dependency is required for judging |
| Historical/live deployment evidence | KEEP AS HISTORICAL/LABELLED | Does not prove the W6/W7 candidate or a currently reachable service |
| Generic coding agent, arbitrary shell/process, raw file write, Git mutation or package install | CUT / NOT IMPLEMENTED | Would broaden authority and is outside the hackathon product |
| Browser/MCP control and active-user-browser integration | CUT / NOT IMPLEMENTED | Depends on private state and adds risk without core judging value |
| Public multi-user identity, hosted durable recovery and rate-limited tenancy | CUT / NOT IMPLEMENTED | Not certified and must not be implied by local single-operator evidence |
| Live AWS remediation in the core demo | CUT / NOT IMPLEMENTED | Requires external authority and could create mutation/cost risk |
| Workspace-hero screenshots from a personal browser | CUT | No isolated capture was available at W5; tests are evidence, not fabricated screenshots |

## Frozen authority rules

- Model output is never execution authority.
- Human approval is never terminal success.
- Patch application is never terminal success.
- Executor acknowledgement is never verifier truth.
- `SUCCESS_WITH_EVIDENCE` requires a separately persisted independent verification report and
  terminal receipt.
- Stale, replayed, cross-run, cross-workspace, cross-proposal and cross-session authority fails
  closed.
- W7/W8 cannot add shell, generic filesystem mutation, Git, package, browser/MCP, arbitrary URL,
  deployment or AWS capability.
- Mock/default-deny/AWS-disabled operation, zero external egress and no paid dependency remain
  release requirements.

## Frozen public claim vocabulary

| Label | Meaning |
| --- | --- |
| `LIVE` | Only a later human smoke test of an actually reachable service and its deployed source identity |
| `LOCALLY_PROVEN` | Deterministic tests, clean-clone, local process or container evidence for the exact source candidate |
| `MOCK_DETERMINISTIC` | Workspace and CloudOps demo behavior using fixed local mock providers/state |
| `OPTIONAL` | Existing Bedrock/AWS integration that is not required, configured or exercised by the core demo |
| `NOT_IMPLEMENTED` | Generic coding/shell/Git/package/browser/MCP authority, hosted multi-user durability and other unbuilt capabilities |

Any W7 packaging correction must preserve this table and receive complete B5/B6 recertification.

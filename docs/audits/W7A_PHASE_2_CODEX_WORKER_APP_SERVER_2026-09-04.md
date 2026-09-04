# W7A Phase 2 — Codex Worker / App Server — 2026-09-04

## Gate status

`PHASE_2_RESULT=PROVISIONAL_PASS_PENDING_CLEAN_COMMIT_GATE`

The implementation and live worker proof are green. The only remaining Phase 2 closure action at
the time of this checkpoint is to commit the exact candidate and rerun P1-06 clean-clone plus B4
against a clean worktree. P1-06 correctly reported `SOURCE_WORKTREE_NOT_CLEAN` while these Phase 2
files were uncommitted; that result is not represented as a product failure or as a PASS.

This audit is W7A development evidence. It is not canonical B5/B6 evidence and does not modify or
recertify the frozen release candidate.

## Implemented boundary

- `CodingWorker` defines start, task submission, event streaming, result receipt,
  pause/interrupt, cancellation, and close without any GitHub/AWS credential or remote-write field.
- `WorkerTask`, `WorkerSession`, `WorkerTaskHandle`, `WorkerEvent`, `WorkerCommandResult`, and
  `WorkerResult` are strict immutable Pydantic contracts.
- `CodexAppServerWorker` negotiates protocol v2 through `initialize` / `initialized`, creates an
  ephemeral `thread/start`, starts one bounded `turn/start`, captures item/command/diff events, and
  accepts terminal success only from a matching `turn/completed` status.
- `JsonlFramer` handles partial frames, multiple frames, blank lines, malformed JSON, non-object
  JSON, oversized frames, and truncated EOF deterministically.
- JSON-RPC request IDs have dedicated response queues and deadlines. Late or unmatched responses
  cannot be attached to another request.
- The transport event queue is bounded. Overflow terminates only the owned App Server process.
- All server-initiated approval, permission, elicitation, user-input, and dynamic-tool requests are
  denied through explicit response contracts or a stable JSON-RPC policy error.
- Cancellation is idempotent and terminal. Timeout, crash, protocol error, and out-of-workspace
  paths cannot produce a success/diff claim.
- Stderr is separate from stdout protocol transport, size-bounded, and redacted.

## Process and sandbox contract

The old repository security invariant rejecting `subprocess` in executable source remains intact.
The real adapter uses a small `OwnedProcess` based on `os.pipe2` and `os.posix_spawnp`:

- structured argv only; no shell and no command-string parsing;
- a new owned session/process group;
- three owned pipes and deterministic descriptor closure;
- bounded graceful shutdown followed by group kill only for the exact child;
- canonical, operator-owned, non-symlink workspace root;
- `approvalPolicy=never`, `sandbox=workspace-write`, and an explicit writable root equal to the
  disposable fixture;
- tool network disabled, `/tmp` implicit authority excluded, and no environment-root expansion;
- tool environment inheritance disabled, with only fixed `PATH`, `LANG`, and
  `PYTHONDONTWRITEBYTECODE` values supplied.

The trusted App Server process may retain existing OpenAI model authentication. Its environment
removes `AWS_*`, `GITHUB_*`, `GH_*`, `SSH_*`, generic token/secret/password variables, and non-model
API keys. No credential is placed in the task, fixture, event, result, diagnostics, or diff.

## Current protocol discovery

- Installed CLI: `codex-cli 0.151.0`
- Command: `codex app-server --stdio`
- Generated schema command:
  `codex app-server generate-json-schema --experimental --out <temporary-directory>`
- Current lifecycle used: `initialize`, `initialized`, `thread/start`, `turn/start`,
  `turn/started`, `item/started`, `item/completed`, `turn/diff/updated`, `turn/completed`, and
  `turn/interrupt`.
- Explicit non-authorizing notifications observed and allowlisted include remote-control status,
  MCP startup status, thread settings/token/status, and account/rate-limit status. Unknown methods
  still fail closed.
- Official integration reference:
  `https://developers.openai.com/codex/app-server`

## Real disposable-fixture proof

The tracked probe `scripts/run_w7a_codex_worker_probe.py` created a private temporary workspace with
one buggy source file and one `unittest` file. It invoked the installed App Server, with model tool
network disabled, and requested only the source correction.

Final observation:

```text
LIVE_APP_SERVER=PASS
WORKER_STATUS=SUCCESS
EVENTS=41
CHANGED_FILES=solver.py
LOCAL_TEST_COMMAND=PASS
SOURCE_CORRECT=YES
UNEXPECTED_FIXTURE_FILES=0
PROTOCOL_DIAGNOSTICS=EMPTY
GITHUB_MUTATIONS=0
AWS_CALLS=0
```

The real AIOA repository was never the worker workspace. The temporary fixture was destroyed by
the probe after result validation.

## Adversarial and regression evidence

- Focused Phase 2 contract suite: `25/25 PASS`; after the owned-process refinement and legacy
  security nodes: `27/27 PASS`.
- Full regression, final exact source candidate: `1764/1764 PASS` in `779.72s`.
- Earlier diagnostic full runs are retained honestly:
  - `1763 PASS / 1 FAIL`: old static `subprocess` prohibition identified the first launcher;
    implementation was redesigned without changing that test.
  - `1763 PASS / 1 FAIL`: independent W4 runtime cleanup flake; the exact failed node immediately
    reran `1/1 PASS`, then the final full suite passed.
- P0: `15/15 PASS`, `0 FAIL`, `0 SKIP`.
- P1 before commit: `5/6 PASS`; P1-06 command proof correctly blocked on
  `SOURCE_WORKTREE_NOT_CLEAN`. Post-commit rerun is mandatory.
- Secret scan: `PASS`, `0 findings`, `501 files scanned`, values not emitted.
- Ruff: `PASS`.
- pip check: `PASS`.
- `git diff --check`: `PASS`.

## Known limitations

- The owned-process implementation targets the discovered Linux/POSIX runtime and requires an
  `env` implementation supporting `--chdir`.
- Protocol compatibility is deliberately tied to current generated v2 shapes. A future unknown
  required method fails closed until reviewed.
- Worker output is a non-authoritative candidate. General PatchSet policy, independent validation,
  remote write authority, package installation, and GitHub writes remain outside Phase 2.

## Invariants

```text
MODEL_OUTPUT_IS_EXECUTION_AUTHORITY=NO
WORKER_SUCCESS_IS_VERIFIED_REMOTE_SUCCESS=NO
WORKER_HAS_GITHUB_WRITE_CREDENTIAL=NO
WORKER_HAS_AWS_CREDENTIAL=NO
WORKER_HAS_SSH_AGENT=NO
RUNTIME_GITHUB_WRITES=0
AWS_CALLS=0
DEPLOYMENTS=0
W7_FROZEN_HEAD=945c87052815b237004d259fe993cc92cbd579b7
W7_B5_B6_RECERTIFIED=NO
W8_EXECUTED=NO
```


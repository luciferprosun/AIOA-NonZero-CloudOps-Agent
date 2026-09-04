#!/usr/bin/env python3
"""Run the W7A Phase 2 live Codex worker proof in a disposable fixture."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from aioa_cloudops_agent.agent import (
    SubprocessJsonRpcTransport,
    WorkerTask,
    WorkerTerminalStatus,
    WorkerWorkspaceIdentity,
    digest_workspace_tree,
    run_codex_worker_task,
)
from aioa_cloudops_agent.nz import generate_event_id, generate_run_id


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="aioa-w7a-codex-worker-") as temporary:
        root = Path(temporary).resolve()
        (root / "solver.py").write_text(
            "def add(left: int, right: int) -> int:\n    return left - right\n",
            encoding="utf-8",
        )
        (root / "test_solver.py").write_text(
            "import unittest\n\n"
            "from solver import add\n\n\n"
            "class SolverTest(unittest.TestCase):\n"
            "    def test_add(self) -> None:\n"
            "        self.assertEqual(add(2, 3), 5)\n\n\n"
            "if __name__ == '__main__':\n"
            "    unittest.main()\n",
            encoding="utf-8",
        )
        task = WorkerTask(
            run_id=generate_run_id(),
            task_id=generate_event_id(),
            workspace=WorkerWorkspaceIdentity(
                workspace_id=generate_event_id(),
                root_path=root.as_posix(),
                expected_base_digest=digest_workspace_tree(root),
            ),
            instruction=(
                "This is a disposable test fixture. Inspect solver.py and test_solver.py. Change "
                "only solver.py so `python -m unittest -q` passes. Do not use network. Do not "
                "access paths outside this workspace. Run that exact test and finish with a short "
                "summary."
            ),
            timeout_seconds=240,
        )
        transport = SubprocessJsonRpcTransport()
        events, result = run_codex_worker_task(task, transport=transport)
        changed = tuple(
            path.relative_to(root).as_posix()
            for path in sorted(root.rglob("*"))
            if path.is_file() and path.name not in {"solver.py", "test_solver.py"}
        )
        source_correct = "return left + right" in (root / "solver.py").read_text(
            encoding="utf-8"
        )
        command_pass = any(
            command.status == "completed" and command.exit_code == 0
            for command in result.commands
        )
        passed = (
            result.status is WorkerTerminalStatus.SUCCESS
            and result.changed_files == ("solver.py",)
            and bool(result.candidate_diff)
            and source_correct
            and command_pass
            and not changed
        )
        print(
            json.dumps(
                {
                    "status": "PASS" if passed else "FAIL",
                    "worker_status": result.status,
                    "event_count": len(events),
                    "event_sources": tuple(event.source_method for event in events),
                    "failure_code": result.failure_code,
                    "changed_files": result.changed_files,
                    "diff_sha256": hashlib.sha256(
                        result.candidate_diff.encode("utf-8")
                    ).hexdigest(),
                    "test_command_pass": command_pass,
                    "source_correct": source_correct,
                    "unexpected_fixture_files": changed,
                    "github_mutations": result.github_mutations,
                    "protocol_diagnostics": transport.diagnostics()[-2048:],
                    "aws_calls": result.aws_calls,
                },
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

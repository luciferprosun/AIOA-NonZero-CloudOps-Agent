import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from aioa_cloudops_agent.nz import (
    BudgetCounters,
    Run,
    StorageConflictError,
    StorageDependencyError,
    WorkflowState,
)
from aioa_cloudops_agent.persistence import LocalFileDurableTruthRepository

RUN_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3a")
TRACE_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3b")
CORRELATION_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3c")
NOW = datetime(2026, 8, 26, 10, 0, tzinfo=UTC)


def _run() -> Run:
    return Run.new(
        run_id=RUN_ID,
        trace_id=TRACE_ID,
        correlation_id=CORRELATION_ID,
        idempotency_key="local/store/0001",
        created_at=NOW,
        budget=BudgetCounters(max_turns=8, max_tokens=2_048),
    )


class FailingWriteStore(LocalFileDurableTruthRepository):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.fail_next_write = False

    def _write(self, repository: object) -> None:
        if self.fail_next_write:
            self.fail_next_write = False
            raise StorageDependencyError("injected local write failure")
        super()._write(repository)


def test_local_store_crud_and_restart_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = LocalFileDurableTruthRepository(path)
    created = store.create_run(_run())
    running = store.transition_run(
        created.run_id,
        WorkflowState.INVESTIGATING,
        expected_state=WorkflowState.RECEIVED,
        expected_version=created.version,
        updated_at=NOW,
    )

    reopened = LocalFileDurableTruthRepository(path)
    assert reopened.get_run(RUN_ID) == running
    assert path.stat().st_mode & 0o777 == 0o600


def test_local_store_rejects_stale_writer_without_changing_state(tmp_path: Path) -> None:
    store = LocalFileDurableTruthRepository(tmp_path / "state.json")
    created = store.create_run(_run())
    running = store.transition_run(
        created.run_id,
        WorkflowState.INVESTIGATING,
        expected_state=WorkflowState.RECEIVED,
        expected_version=created.version,
        updated_at=NOW,
    )

    with pytest.raises(StorageConflictError, match="version"):
        store.transition_run(
            created.run_id,
            WorkflowState.INVESTIGATING,
            expected_state=WorkflowState.RECEIVED,
            expected_version=created.version,
            updated_at=NOW,
        )
    assert store.get_run(RUN_ID) == running


def test_failed_transition_write_leaves_persisted_state_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = FailingWriteStore(path)
    created = store.create_run(_run())
    store.fail_next_write = True

    with pytest.raises(StorageDependencyError, match="injected"):
        store.transition_run(
            created.run_id,
            WorkflowState.INVESTIGATING,
            expected_state=WorkflowState.RECEIVED,
            expected_version=created.version,
            updated_at=NOW,
        )

    reopened = LocalFileDurableTruthRepository(path)
    assert reopened.get_run(RUN_ID) == created


@pytest.mark.parametrize(
    "content",
    [
        "{not-json",
        json.dumps({"format_version": 999}),
        json.dumps(
            {
                "format_version": 1,
                "runs": [{"state": "UNKNOWN"}],
                "proposals": [],
                "approvals": [],
                "idempotency": [],
                "checkpoints": [],
                "audit_events": [],
                "verification_evidence": [],
            }
        ),
    ],
)
def test_corrupt_or_unknown_local_state_fails_closed(tmp_path: Path, content: str) -> None:
    path = tmp_path / "state.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(StorageDependencyError):
        LocalFileDurableTruthRepository(path).get_run(RUN_ID)


def test_duplicate_run_creation_is_typed_conflict(tmp_path: Path) -> None:
    store = LocalFileDurableTruthRepository(tmp_path / "state.json")
    store.create_run(_run())

    with pytest.raises(StorageConflictError, match="already exists"):
        store.create_run(_run())

"""Integrity checks for the resumed W7A Phase 4 certification evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECEIPT = ROOT / "docs/evidence/w7a/phase4-runtime-certification.json"
AUDIT = ROOT / "docs/audits/W7A_PHASE_4_SANDBOX_SETUP_INSTALLER_2026-09-04.md"
IMPLEMENTATION_COMMIT = "1454eec76bd9eaf848a1e784b78ac365d990dc1b"
IMAGE_SHA256 = "7f4e8f00a1ea130d7b30b8371911239f6bf3df4131533faf04df667668739df7"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def test_phase4_receipt_is_self_hashed_and_fail_closed() -> None:
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    claimed = receipt.pop("receipt_sha256")

    assert claimed == hashlib.sha256(_canonical_bytes(receipt)).hexdigest()
    assert receipt["authority"] == "W7A_PHASE_4_RUNTIME_CERTIFICATION"
    assert receipt["status"] == "PASS"
    assert receipt["implementation_source_commit"] == IMPLEMENTATION_COMMIT
    assert receipt["toolbox"]["image_sha256"] == IMAGE_SHA256
    assert receipt["toolbox"]["source_commit"] == IMPLEMENTATION_COMMIT
    assert receipt["runtime"]["setup_network"] == "NONE"
    assert receipt["runtime"]["coding_network"] == "NONE"
    assert receipt["runtime"]["run_as"] == "65532:65532"
    assert receipt["runtime"]["orphaned_resources"] == 0
    assert receipt["runtime"]["repository_code_during_setup"] == "DENIED"
    assert receipt["secret_findings"] == 0
    assert receipt["aws_calls"] == 0
    assert receipt["aws_mutations"] == 0
    assert receipt["external_deployments"] == 0
    assert receipt["product_github_mutations"] == 0


def test_phase4_audit_preserves_historical_blocker_before_resumed_pass() -> None:
    audit = AUDIT.read_text(encoding="utf-8")

    historical = audit.index("PHASE_4_RESULT=PARTIAL_DOCKER_UNAVAILABLE")
    resumed = audit.index("## Resumed runtime certification")
    current = audit.rindex("PHASE_4_RESULT=PASS")
    assert historical < resumed < current
    assert IMPLEMENTATION_COMMIT in audit
    assert IMAGE_SHA256 in audit

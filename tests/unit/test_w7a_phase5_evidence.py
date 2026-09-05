"""Integrity and authority checks for the W7A Phase 5 certification receipt."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from aioa_cloudops_agent.patchset import MAX_CHANGED_LINES, MAX_FILES_CHANGED

ROOT = Path(__file__).resolve().parents[2]
RECEIPT = ROOT / "docs/evidence/w7a/phase5-patchset-certification.json"
IMPLEMENTATION_COMMIT = "f2b2f60003637c03df29d613da62c77877ef9c1e"
FROZEN_W7_HEAD = "945c87052815b237004d259fe993cc92cbd579b7"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def test_phase5_receipt_is_self_hashed_and_fail_closed() -> None:
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    claimed = receipt.pop("receipt_sha256")

    assert claimed == hashlib.sha256(_canonical_bytes(receipt)).hexdigest()
    assert receipt["authority"] == "W7A_PHASE_5_PATCHSET_CERTIFICATION"
    assert receipt["status"] == "PASS"
    assert receipt["implementation_source_commit"] == IMPLEMENTATION_COMMIT
    assert receipt["frozen_w7_b5_b6_head"] == FROZEN_W7_HEAD
    assert receipt["patchset_policy"]["max_files_changed"] == MAX_FILES_CHANGED == 3
    assert receipt["patchset_policy"]["max_changed_lines"] == MAX_CHANGED_LINES == 300
    assert receipt["patchset_policy"]["model_claim_authoritative"] is False
    assert receipt["patchset_policy"]["provider_neutral"] is True
    assert receipt["patchset_policy"]["toctou_recheck"] == "PASS"
    assert receipt["secret_findings"] == 0
    assert receipt["aws_calls"] == 0
    assert receipt["aws_mutations"] == 0
    assert receipt["external_deployments"] == 0
    assert receipt["product_github_mutations"] == 0


def test_phase5_receipt_binds_all_required_regression_gates() -> None:
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))

    assert receipt["focused_tests"] == {
        "failed": 0,
        "passed": 372,
        "skipped": 0,
        "status": "PASS",
    }
    assert receipt["full_pytest"]["passed"] == 1887
    assert receipt["full_pytest"]["failed"] == 0
    assert receipt["p0"]["gates_passed"] == 15
    assert receipt["p1"]["gates_passed"] == 6
    assert receipt["b4"]["scenarios_passed"] == 11
    assert receipt["clean_clone"]["commit"] == IMPLEMENTATION_COMMIT
    assert receipt["clean_clone"]["status"] == "PASS"

"""Integrity and authority checks for W7A Phase 6 evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from aioa_cloudops_agent.repair_loop import MAX_REPAIR_ATTEMPTS

ROOT = Path(__file__).resolve().parents[2]
E2E_RECEIPT = ROOT / "docs/evidence/w7a/phase6-real-local-e2e.json"
CERTIFICATION = ROOT / "docs/evidence/w7a/phase6-loop-certification.json"
IMPLEMENTATION_COMMIT = "88d41b1721914f13588319883c85656953b1bf2a"
TOOLBOX_IMAGE = "7f4e8f00a1ea130d7b30b8371911239f6bf3df4131533faf04df667668739df7"
FROZEN_W7_HEAD = "945c87052815b237004d259fe993cc92cbd579b7"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def test_phase6_real_e2e_receipt_is_self_hashed_and_non_authoritative_claims_lose() -> None:
    envelope = json.loads(E2E_RECEIPT.read_text(encoding="utf-8"))
    receipt = envelope["receipt"]

    assert envelope["receipt_sha256"] == hashlib.sha256(_canonical_bytes(receipt)).hexdigest()
    assert receipt["authority"] == "W7A_PHASE_6_REAL_LOCAL_E2E"
    assert receipt["status"] == "PASS"
    assert receipt["base_head"] == IMPLEMENTATION_COMMIT
    assert receipt["toolbox_image_sha256"] == TOOLBOX_IMAGE
    assert receipt["real_codex_worker"] == "PASS"
    assert receipt["real_docker_sandbox"] == "PASS"
    assert receipt["initial_targeted_test"]["exit_code"] == 1
    assert receipt["initial_targeted_test"]["network_mode"] == "NONE"
    assert receipt["worker_claim_authoritative"] is False
    assert receipt["worker_claim_matched_actual"] is False
    assert receipt["worker_host_code_test_commands"] == 0
    assert receipt["final_files"] == ["solver.py"]
    assert receipt["sandbox_cleanup_orphans"] == 0
    assert receipt["sandbox_independent_orphans"] == 0
    assert receipt["product_github_mutations"] == 0
    assert receipt["aws_calls"] == 0
    assert receipt["aws_mutations"] == 0
    assert receipt["external_deployments"] == 0


def test_phase6_certification_is_self_hashed_and_binds_every_pass_gate() -> None:
    receipt = json.loads(CERTIFICATION.read_text(encoding="utf-8"))
    claimed = receipt.pop("receipt_sha256")

    assert claimed == hashlib.sha256(_canonical_bytes(receipt)).hexdigest()
    assert receipt["authority"] == "W7A_PHASE_6_LOOP_CERTIFICATION"
    assert receipt["status"] == "PASS"
    assert receipt["implementation_source_commit"] == IMPLEMENTATION_COMMIT
    assert receipt["frozen_w7_b5_b6_head"] == FROZEN_W7_HEAD
    assert receipt["toolbox"]["image_sha256"] == TOOLBOX_IMAGE
    assert receipt["phase4"]["status"] == "PASS"
    assert receipt["phase5"]["status"] == "PASS"
    assert receipt["focused_tests"]["passed"] == 388
    assert receipt["full_pytest"]["passed"] == 1901
    assert receipt["p0"]["gates_passed"] == 15
    assert receipt["p1"]["gates_passed"] == 6
    assert receipt["b4"]["scenarios_passed"] == 11
    assert receipt["clean_clone"] == {
        "commit": IMPLEMENTATION_COMMIT,
        "mode": "local-no-local",
        "status": "PASS",
    }
    loop = receipt["repair_loop"]
    assert loop["max_repair_attempts"] == MAX_REPAIR_ATTEMPTS == 2
    assert loop["max_repair_attempts_enforced"] is True
    assert loop["each_repair_new_patchset_hash"] == "PASS"
    assert loop["repair_exhaustion_closed"] == "PASS"
    assert loop["anti_test_weakening"] == "PASS"
    assert loop["final_review"] == "PASS"
    assert loop["final_policy_recheck"] == "PASS"
    assert loop["final_secret_scan"] == "PASS"
    assert loop["final_tests_gates"] == "PASS"
    assert loop["unknown_ambiguous_timeout_crash_is_pass"] is False
    assert loop["sandbox_cleanup_orphans"] == 0
    assert receipt["secret_scan"]["findings"] == 0
    assert receipt["aws_calls"] == 0
    assert receipt["aws_mutations"] == 0
    assert receipt["external_deployments"] == 0
    assert receipt["product_github_mutations"] == 0

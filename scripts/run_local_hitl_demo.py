"""Run one complete credential-free Local-2 human authorization scenario."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from aioa_cloudops_agent.agent import (
    LocalDecisionRequest,
    LocalOperatorPrincipal,
    create_local_hitl_runtime,
)
from aioa_cloudops_agent.cloudops import (
    MOCK_UNATTACHED_EIP_ID,
    MOCK_UNSAFE_SECURITY_GROUP_ID,
)
from aioa_cloudops_agent.config import LocalHitlSettings
from aioa_cloudops_agent.nz import (
    ApprovalDecision,
    BudgetCounters,
    CloudResourceType,
    ResourceQuery,
    ResultStatus,
    Run,
    generate_run_id,
    generate_trace_id,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=("elastic-ip", "security-group"),
        default="elastic-ip",
    )
    parser.add_argument(
        "--decision",
        choices=("approved", "denied"),
        default="approved",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".local/aioa-local2-demo"),
    )
    return parser.parse_args()


def _fail(stage: str, result: object) -> int:
    failure = getattr(result, "failure", None)
    payload = {
        "ok": False,
        "stage": stage,
        "failure": (
            failure.model_dump(mode="json", exclude_none=True)
            if failure is not None
            else {"code": "AMBIGUOUS_DEMO_FAILURE"}
        ),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1


def main() -> int:
    args = _arguments()
    run_id = generate_run_id()
    output_dir = args.output_dir / str(run_id)
    settings = LocalHitlSettings(
        state_path=output_dir / "durable-truth.json",
        inventory_path=output_dir / "mock-inventory.json",
    )
    runtime = create_local_hitl_runtime(settings)
    now = datetime.now(UTC)
    run = Run.new(
        run_id=run_id,
        trace_id=generate_trace_id(),
        correlation_id=generate_trace_id(),
        idempotency_key=f"local/demo/{run_id}",
        created_at=now,
        budget=BudgetCounters(max_turns=8, max_tokens=2_048),
    )
    target = (
        (CloudResourceType.ELASTIC_IP, MOCK_UNATTACHED_EIP_ID)
        if args.scenario == "elastic-ip"
        else (CloudResourceType.SECURITY_GROUP, MOCK_UNSAFE_SECURITY_GROUP_ID)
    )
    planned = runtime.phase_one.execute(
        run,
        ResourceQuery(resource_type=target[0], resource_id=target[1]),
    )
    if planned.status is ResultStatus.FAILURE or planned.value is None:
        return _fail("plan", planned)
    principal = LocalOperatorPrincipal(actor_session_id="local-demo-operator")
    challenge = runtime.phase_two.request_approval(run_id, principal)
    if challenge.status is ResultStatus.FAILURE or challenge.value is None:
        return _fail("approval_request", challenge)
    request = challenge.value.request
    selected_decision = ApprovalDecision(args.decision.upper())
    decided = runtime.phase_two.decide(
        LocalDecisionRequest(
            request_id=request.request_id,
            run_id=request.run_id,
            proposal_id=request.proposal_id,
            request_hash=request.request_hash,
            proposal_hash=request.proposal_hash,
            evidence_hash=request.evidence_hash,
            proposal_version=request.proposal_version,
            decision=selected_decision,
            decision_nonce=challenge.value.decision_nonce,
        ),
        principal,
    )
    if decided.status is ResultStatus.FAILURE or decided.value is None:
        return _fail("decision", decided)
    completed = runtime.phase_two.resume(run_id, principal)
    if completed.status is ResultStatus.FAILURE or completed.value is None:
        return _fail("resume", completed)
    receipt = completed.value.receipt
    verification = completed.value.verification
    payload = {
        "decision": selected_decision.value,
        "evidence_hash": planned.value.evidence.evidence_hash,
        "final_state": completed.value.final_state.value,
        "mock_mutation_count": runtime.executor.mutation_calls,
        "network_calls": runtime.cloud_provider.network_calls,
        "ok": True,
        "operation": planned.value.plan.proposal.operation_type.value,
        "output_dir": str(output_dir),
        "proposal_hash": planned.value.plan.proposal.proposal_hash,
        "receipt_hash": receipt.receipt_hash if receipt is not None else None,
        "run_id": str(run_id),
        "verification_hash": (
            verification.verification_hash if verification is not None else None
        ),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

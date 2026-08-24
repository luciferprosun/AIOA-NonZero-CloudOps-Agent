from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _document(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_au2_is_evaluation_only_and_deferred_after_submission() -> None:
    document = _document("docs/architecture/au-2-risk-evaluation.md")

    assert "AU2_IMPLEMENTED = NO" in document
    assert "AU2_RISK = HIGH" in document
    assert "AU2_RECOMMENDATION = DEFER_UNTIL_AFTER_SUBMISSION" in document
    assert "separate versioned chain-head record" in document


def test_day15_handoff_is_complete_but_does_not_authorize_deployment() -> None:
    document = _document("docs/architecture/day-15-deployment-readiness.md")

    assert "READY_FOR_DAY_15_IMPLEMENTATION_PACKAGE = YES" in document
    assert "READY_FOR_DAY_15_DEPLOYMENT = NO" in document
    assert "DEPLOY_NOW = NO" in document
    assert "AWS_DEPLOYMENT_PERFORMED = NO" in document
    assert "LIVE_STOPINSTANCES_CALLED = NO" in document
    assert "AGENTCORE_ALLOWED = NO" in document
    assert all(f"D15-{index:02d}" in document for index in range(1, 19))
    assert "AWS_MUTATIONS_ENABLED=false" in document
    assert "AIOA_ALLOW_LIVE_SANDBOX_STOP=false" in document
    assert "AIOA_EMERGENCY_EXECUTION_DISABLED=true" in document
    assert "total_max_attempts: 1" in document
    assert "AuthType: NONE" in document
    assert "lambda:InvokeFunctionUrl" in document
    assert "lambda:FunctionUrlAuthType=NONE" in document
    assert "lambda:InvokedViaFunctionUrl=true" in document
    assert "sam deploy" not in document.casefold()


def test_roadmap_records_day14_completion_and_day15_boundary() -> None:
    document = _document("docs/ROADMAP_STATUS.md")

    assert "DAY_14_P1_PROOF_GATE = COMPLETE_EXECUTABLE_6_OF_6_ZERO_SKIPS" in document
    assert "AU3_REVIEWER_EVIDENCE_MANIFEST = COMPLETE_DETERMINISTIC_19_CLAIMS" in document
    assert "DAY_14 = COMPLETE_LOCAL_P1_AND_AU3" in document
    assert "DAY_15_DEPLOYMENT = NOT_STARTED_READINESS_BLOCKERS_DOCUMENTED" in document

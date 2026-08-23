import json
import re
from pathlib import Path

IAM_DIRECTORY = Path(__file__).parents[2] / "infra" / "iam"
READ_ONLY_POLICY_PATH = IAM_DIRECTORY / "cloudops-read-only-policy.json"
REMEDIATION_POLICY_PATH = IAM_DIRECTORY / "cloudops-remediation-policy.json"
ORCHESTRATOR_POLICY_PATH = IAM_DIRECTORY / "cloudops-orchestrator-policy.json"


def _policy_actions(policy: dict[str, object]) -> list[str]:
    actions: list[str] = []
    for statement in policy["Statement"]:
        value = statement["Action"]
        actions.extend([value] if isinstance(value, str) else value)
    return actions


def test_active_cloudops_policy_allows_only_targeted_read_apis() -> None:
    policy = json.loads(READ_ONLY_POLICY_PATH.read_text(encoding="utf-8"))

    assert _policy_actions(policy) == [
        "ec2:DescribeInstances",
        "cloudwatch:GetMetricStatistics",
    ]
    statement = policy["Statement"][0]
    assert statement["Effect"] == "Allow"
    assert statement["Condition"] == {
        "StringEquals": {"aws:RequestedRegion": "eu-central-1"}
    }


def test_private_executor_policy_is_exact_instance_and_tag_scoped() -> None:
    policy = json.loads(REMEDIATION_POLICY_PATH.read_text(encoding="utf-8"))
    statement = policy["Statement"][0]

    assert _policy_actions(policy) == ["ec2:StopInstances"]
    assert statement["Resource"] == (
        "arn:${AWS::Partition}:ec2:${AWS::Region}:${AWS::AccountId}:"
        "instance/${SandboxInstanceId}"
    )
    assert statement["Condition"] == {
        "StringEquals": {
            "aws:RequestedRegion": "eu-central-1",
            "aws:ResourceTag/AIOACloudOpsSandbox": "true",
        }
    }


def test_orchestrator_can_invoke_only_private_executor_and_cannot_stop_ec2() -> None:
    policy = json.loads(ORCHESTRATOR_POLICY_PATH.read_text(encoding="utf-8"))

    assert _policy_actions(policy) == ["lambda:InvokeFunction"]
    assert policy["Statement"][0]["Resource"] == "${RemediationExecutorFunctionArn}"
    assert "ec2:StopInstances" not in _policy_actions(policy)


def test_iam_templates_have_no_wildcard_action_or_account_id() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in IAM_DIRECTORY.glob("*.json")
    )
    policies = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in IAM_DIRECTORY.glob("*.json")
    ]

    assert all("*" not in action for policy in policies for action in _policy_actions(policy))
    assert re.search(r"(?<!\d)\d{12}(?!\d)", combined) is None
    assert "AdministratorAccess" not in combined
    assert "PowerUserAccess" not in combined


def test_eip_experiment_permission_is_not_active() -> None:
    policy = json.loads(READ_ONLY_POLICY_PATH.read_text(encoding="utf-8"))

    assert "ec2:DescribeAddresses" not in _policy_actions(policy)


def test_no_destructive_or_generalized_write_permission_exists() -> None:
    actions = [
        action
        for path in IAM_DIRECTORY.glob("*.json")
        for action in _policy_actions(json.loads(path.read_text(encoding="utf-8")))
    ]

    assert "ec2:StopInstances" in actions
    for forbidden in (
        "ec2:TerminateInstances",
        "ec2:StartInstances",
        "ec2:RebootInstances",
        "ec2:ModifyInstanceAttribute",
        "ssm:SendCommand",
    ):
        assert forbidden not in actions

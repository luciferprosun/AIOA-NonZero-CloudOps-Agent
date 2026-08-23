import json
import re
from pathlib import Path

IAM_DIRECTORY = Path(__file__).parents[2] / "infra" / "iam"
READ_ONLY_POLICY_PATH = IAM_DIRECTORY / "cloudops-read-only-policy.json"
REMEDIATION_POLICY_PATH = IAM_DIRECTORY / "cloudops-remediation-policy.json"


def _policy_actions(policy: dict[str, object]) -> list[str]:
    actions: list[str] = []
    for statement in policy["Statement"]:
        value = statement["Action"]
        actions.extend([value] if isinstance(value, str) else value)
    return actions


def test_active_cloudops_policy_allows_only_targeted_inspection_api() -> None:
    policy = json.loads(READ_ONLY_POLICY_PATH.read_text(encoding="utf-8"))

    assert _policy_actions(policy) == ["ec2:DescribeInstances"]
    statement = policy["Statement"][0]
    assert statement["Effect"] == "Allow"
    assert statement["Condition"] == {
        "StringEquals": {"aws:RequestedRegion": "eu-central-1"}
    }


def test_no_remediation_policy_is_active() -> None:
    assert REMEDIATION_POLICY_PATH.exists() is False


def test_iam_templates_have_no_wildcard_action_or_account_id() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in IAM_DIRECTORY.glob("*.json")
    )
    policy = json.loads(READ_ONLY_POLICY_PATH.read_text(encoding="utf-8"))

    assert all("*" not in action for action in _policy_actions(policy))
    assert re.search(r"(?<!\d)\d{12}(?!\d)", combined) is None
    assert "AdministratorAccess" not in combined
    assert "PowerUserAccess" not in combined


def test_eip_experiment_permission_is_not_active() -> None:
    policy = json.loads(READ_ONLY_POLICY_PATH.read_text(encoding="utf-8"))

    assert "ec2:DescribeAddresses" not in _policy_actions(policy)

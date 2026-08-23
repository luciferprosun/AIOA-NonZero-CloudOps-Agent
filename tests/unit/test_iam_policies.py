import json
import re
from pathlib import Path

IAM_DIRECTORY = Path(__file__).parents[2] / "infra" / "iam"


def _load_policy(filename: str) -> dict[str, object]:
    return json.loads((IAM_DIRECTORY / filename).read_text(encoding="utf-8"))


def _policy_actions(policy: dict[str, object]) -> set[str]:
    actions: set[str] = set()
    for statement in policy["Statement"]:
        value = statement["Action"]
        actions.update([value] if isinstance(value, str) else value)
    return actions


def test_read_only_policy_has_only_initial_discovery_actions() -> None:
    policy = _load_policy("cloudops-read-only-policy.json")

    assert _policy_actions(policy) == {
        "ec2:DescribeAddresses",
        "ec2:DescribeInstances",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeTags",
    }
    assert policy["Statement"][0]["Resource"] == "*"


def test_remediation_policy_is_limited_to_tagged_elastic_ip_release() -> None:
    policy = _load_policy("cloudops-remediation-policy.json")
    statement = policy["Statement"][0]

    assert _policy_actions(policy) == {"ec2:ReleaseAddress"}
    assert statement["Resource"] == (
        "arn:${Partition}:ec2:eu-central-1:${Account}:elastic-ip/${AllocationId}"
    )
    assert statement["Condition"]["StringEquals"]["aws:ResourceTag/AIOACloudOpsManaged"] == (
        "true"
    )


def test_iam_templates_have_no_wildcard_actions_or_account_ids() -> None:
    for path in IAM_DIRECTORY.glob("*.json"):
        policy = _load_policy(path.name)
        assert all("*" not in action for action in _policy_actions(policy))
        assert re.search(r"(?<!\d)\d{12}(?!\d)", path.read_text(encoding="utf-8")) is None

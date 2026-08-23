import ast
from pathlib import Path

import yaml

CLOUDOPS_DIRECTORY = Path(__file__).parents[2] / "src" / "aioa_cloudops_agent" / "cloudops"
SAM_TEMPLATE = Path(__file__).parents[2] / "infra" / "sam" / "template.yaml"
FORBIDDEN_CALLS = {
    "authorize_security_group_ingress",
    "delete_security_group",
    "release_address",
    "revoke_security_group_ingress",
    "run_instances",
    "terminate_instances",
}


def _provider_client_calls(path: Path) -> set[str]:
    syntax_tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.func.attr
        for node in ast.walk(syntax_tree)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Attribute)
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "self"
            and node.func.value.attr == "_ec2_client"
        )
    }


def _actions(value: object) -> set[str]:
    actions: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "Action":
                actions.update([child] if isinstance(child, str) else child)
            else:
                actions.update(_actions(child))
    elif isinstance(value, list):
        for child in value:
            actions.update(_actions(child))
    return actions


def test_executable_cloudops_code_contains_no_mutation_call() -> None:
    called_methods: set[str] = set()
    for path in CLOUDOPS_DIRECTORY.glob("*.py"):
        called_methods.update(_provider_client_calls(path))

    assert called_methods.isdisjoint(FORBIDDEN_CALLS)
    assert called_methods == {"describe_addresses"}


def test_deployable_runtime_authority_contains_no_cloudops_mutation() -> None:
    template = yaml.safe_load(SAM_TEMPLATE.read_text(encoding="utf-8"))
    actions = _actions(template)

    assert not any(action.startswith("ec2:") for action in actions)
    assert all("*" not in action for action in actions)

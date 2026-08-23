import json
import re
from pathlib import Path
from typing import Any

import yaml

TEMPLATE_PATH = Path(__file__).parents[2] / "infra" / "sam" / "template.yaml"


def _template() -> dict[str, Any]:
    return yaml.safe_load(TEMPLATE_PATH.read_text(encoding="utf-8"))


def _resources() -> dict[str, Any]:
    return _template()["Resources"]


def _inline_role_actions(role: dict[str, Any]) -> set[str]:
    actions: set[str] = set()
    for policy in role["Properties"].get("Policies", []):
        for statement in policy["PolicyDocument"]["Statement"]:
            value = statement["Action"]
            actions.update([value] if isinstance(value, str) else value)
    return actions


def _all_actions(value: object) -> list[str]:
    actions: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "Action":
                actions.extend([child] if isinstance(child, str) else child)
            else:
                actions.extend(_all_actions(child))
    elif isinstance(value, list):
        for child in value:
            actions.extend(_all_actions(child))
    return actions


def test_template_declares_expected_sam_format() -> None:
    template = _template()

    assert template["AWSTemplateFormatVersion"] == "2010-09-09"
    assert template["Transform"] == "AWS::Serverless-2016-10-31"


def test_health_lambda_has_bounded_python_runtime() -> None:
    function = _resources()["HealthFunction"]
    properties = function["Properties"]

    assert function["Type"] == "AWS::Serverless::Function"
    assert properties["Runtime"] == "python3.12"
    assert properties["Architectures"] == ["x86_64"]
    assert properties["MemorySize"] == 256
    assert properties["Timeout"] == 10
    assert properties["ReservedConcurrentExecutions"] == 2


def test_health_lambda_code_uri_and_handler_exist() -> None:
    properties = _resources()["HealthFunction"]["Properties"]
    code_directory = (TEMPLATE_PATH.parent / properties["CodeUri"]).resolve()
    handler_module, handler_function = properties["Handler"].rsplit(".", maxsplit=1)
    handler_path = code_directory / f"{handler_module.replace('.', '/')}.py"

    assert code_directory == Path(__file__).parents[2] / "src"
    assert handler_path.is_file()
    assert handler_function == "lambda_handler"


def test_only_get_health_route_is_exposed() -> None:
    resources = _resources()
    api = resources["HealthHttpApi"]
    events = resources["HealthFunction"]["Properties"]["Events"]

    assert api["Type"] == "AWS::Serverless::HttpApi"
    assert "CorsConfiguration" not in api["Properties"]
    assert list(events) == ["HealthRoute"]
    assert events["HealthRoute"] == {
        "Type": "HttpApi",
        "Properties": {
            "ApiId": {"Ref": "HealthHttpApi"},
            "Path": "/health",
            "Method": "GET",
        },
    }


def test_health_lambda_receives_only_safe_configuration() -> None:
    variables = _resources()["HealthFunction"]["Properties"]["Environment"]["Variables"]

    assert variables == {
        "APP_STAGE": "hackathon",
        "AWS_MUTATIONS_ENABLED": "false",
        "MODEL_MAX_OUTPUT_TOKENS": "1024",
        "STATE_TABLE_NAME": {"Ref": "StateTable"},
    }


def test_state_table_is_encrypted_on_demand_composite_key_skeleton() -> None:
    table = _resources()["StateTable"]
    properties = table["Properties"]

    assert table["Type"] == "AWS::DynamoDB::Table"
    assert properties["BillingMode"] == "PAY_PER_REQUEST"
    assert properties["SSESpecification"] == {"SSEEnabled": True}
    assert properties["AttributeDefinitions"] == [
        {"AttributeName": "PK", "AttributeType": "S"},
        {"AttributeName": "SK", "AttributeType": "S"},
    ]
    assert properties["KeySchema"] == [
        {"AttributeName": "PK", "KeyType": "HASH"},
        {"AttributeName": "SK", "KeyType": "RANGE"},
    ]
    assert "GlobalSecondaryIndexes" not in properties
    assert "TableName" not in properties


def test_state_persistence_policy_is_table_scoped_and_item_level_only() -> None:
    policy = _resources()["StatePersistencePolicy"]
    statement = policy["Properties"]["PolicyDocument"]["Statement"][0]

    assert policy["Type"] == "AWS::IAM::ManagedPolicy"
    assert set(statement["Action"]) == {
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
    }
    assert statement["Resource"] == {"Fn::GetAtt": ["StateTable", "Arn"]}
    assert "Roles" not in policy["Properties"]
    assert "Users" not in policy["Properties"]
    assert "Groups" not in policy["Properties"]


def test_lambda_execution_role_has_only_log_delivery_permissions() -> None:
    resources = _resources()
    function = resources["HealthFunction"]
    role = resources["HealthFunctionRole"]

    assert role["Type"] == "AWS::IAM::Role"
    assert function["Properties"]["Role"] == {"Fn::GetAtt": ["HealthFunctionRole", "Arn"]}
    assert "ManagedPolicyArns" not in role["Properties"]
    assert _inline_role_actions(role) == {"logs:CreateLogStream", "logs:PutLogEvents"}


def test_lambda_role_has_no_cloudops_or_data_permissions() -> None:
    actions = _inline_role_actions(_resources()["HealthFunctionRole"])

    assert not any(action.startswith("dynamodb:") for action in actions)
    assert not any(action.startswith("ec2:") for action in actions)
    assert not any(action.startswith("bedrock:") for action in actions)
    assert "ec2:ReleaseAddress" not in actions


def test_template_has_no_wildcard_actions_or_broad_managed_policies() -> None:
    template = _template()
    serialized = json.dumps(template, sort_keys=True)

    assert all("*" not in action for action in _all_actions(template))
    assert "AdministratorAccess" not in serialized
    assert "PowerUserAccess" not in serialized


def test_cloudwatch_log_retention_is_three_days() -> None:
    log_group = _resources()["HealthFunctionLogGroup"]

    assert log_group["Type"] == "AWS::Logs::LogGroup"
    assert log_group["Properties"]["RetentionInDays"] == 3


def test_template_contains_no_agentcore_or_account_identifier() -> None:
    template_text = TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "agentcore" not in template_text.lower()
    assert re.search(r"(?<!\d)\d{12}(?!\d)", template_text) is None

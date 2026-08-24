#!/usr/bin/env python3
"""Perform deterministic local checks on the Day 15 SAM template without AWS calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Final

import yaml

ROOT: Final = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE: Final = ROOT / "infra" / "sam" / "template.yaml"
LOGICAL_ID_PATTERN: Final = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,254}$")
ALLOWED_TOP_LEVEL_KEYS: Final = frozenset(
    {
        "AWSTemplateFormatVersion",
        "Conditions",
        "Description",
        "Globals",
        "Mappings",
        "Metadata",
        "Outputs",
        "Parameters",
        "Resources",
        "Rules",
        "Transform",
    }
)
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")


class TemplateFailure(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class CloudFormationLoader(yaml.SafeLoader):
    """Preserve short-form CloudFormation intrinsics as ordinary mappings."""


def _construct_intrinsic(
    loader: CloudFormationLoader,
    tag_suffix: str,
    node: yaml.Node,
) -> dict[str, object]:
    name = f"Fn::{tag_suffix}" if tag_suffix not in {"Ref", "Condition"} else tag_suffix
    if isinstance(node, yaml.ScalarNode):
        value: object = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        value = loader.construct_mapping(node)
    else:
        raise TemplateFailure("TEMPLATE_INTRINSIC_NODE_INVALID")
    return {name: value}


CloudFormationLoader.add_multi_constructor("!", _construct_intrinsic)


def canonical_json(value: object) -> str:
    return json.dumps(
        value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )


def load_template(path: Path) -> dict[str, object]:
    """Load YAML while rejecting duplicate keys and malformed resource shapes."""

    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise TemplateFailure("TEMPLATE_UNAVAILABLE") from error
    if "\t" in raw:
        raise TemplateFailure("TEMPLATE_TAB_FORBIDDEN")
    try:
        template = yaml.load(raw, Loader=CloudFormationLoader)
    except (yaml.YAMLError, TemplateFailure) as error:
        raise TemplateFailure("TEMPLATE_YAML_INVALID") from error
    if not isinstance(template, dict):
        raise TemplateFailure("TEMPLATE_ROOT_INVALID")
    if any(not isinstance(key, str) or key not in ALLOWED_TOP_LEVEL_KEYS for key in template):
        raise TemplateFailure("TEMPLATE_TOP_LEVEL_KEY_INVALID")
    resources = template.get("Resources")
    if not isinstance(resources, dict) or not resources:
        raise TemplateFailure("TEMPLATE_RESOURCES_INVALID")
    for logical_id, resource in resources.items():
        if not isinstance(logical_id, str) or LOGICAL_ID_PATTERN.fullmatch(logical_id) is None:
            raise TemplateFailure("TEMPLATE_LOGICAL_ID_INVALID")
        if not isinstance(resource, dict) or not isinstance(resource.get("Type"), str):
            raise TemplateFailure("TEMPLATE_RESOURCE_INVALID")
        properties = resource.get("Properties", {})
        if not isinstance(properties, dict):
            raise TemplateFailure("TEMPLATE_RESOURCE_PROPERTIES_INVALID")
    return template


def resources_of_type(template: dict[str, object], *types: str) -> dict[str, dict[str, object]]:
    resources = template.get("Resources", {})
    return {
        str(name): resource
        for name, resource in resources.items()
        if isinstance(resource, dict) and resource.get("Type") in types
    }


def has_sam_transform(template: dict[str, object]) -> bool:
    transform = template.get("Transform")
    if isinstance(transform, str):
        return transform == "AWS::Serverless-2016-10-31"
    return isinstance(transform, list) and "AWS::Serverless-2016-10-31" in transform


def _role_logical_id(role: object) -> str | None:
    if not isinstance(role, dict):
        return None
    get_att = role.get("Fn::GetAtt")
    if isinstance(get_att, list) and len(get_att) == 2 and get_att[1] == "Arn":
        return get_att[0] if isinstance(get_att[0], str) else None
    if isinstance(get_att, str) and get_att.endswith(".Arn"):
        return get_att.removesuffix(".Arn")
    return None


def lambda_configuration_model(template: dict[str, object]) -> dict[str, object]:
    """Project function configuration and referenced execution roles, excluding code bytes."""

    functions = resources_of_type(
        template,
        "AWS::Lambda::Function",
        "AWS::Serverless::Function",
    )
    if not functions:
        raise TemplateFailure("LAMBDA_CONFIGURATION_FUNCTIONS_MISSING")
    all_resources = template.get("Resources", {})
    projected_functions: dict[str, object] = {}
    projected_roles: dict[str, object] = {}
    for logical_id, resource in sorted(functions.items()):
        properties = resource.get("Properties", {})
        if not isinstance(properties, dict):
            raise TemplateFailure("LAMBDA_CONFIGURATION_PROPERTIES_INVALID")
        projected_functions[logical_id] = {
            key: value
            for key, value in sorted(properties.items())
            if key not in {"CodeUri", "FunctionName"}
        }
        role_id = _role_logical_id(properties.get("Role"))
        role = all_resources.get(role_id) if isinstance(all_resources, dict) and role_id else None
        if role_id is None or not isinstance(role, dict) or role.get("Type") != "AWS::IAM::Role":
            raise TemplateFailure("LAMBDA_CONFIGURATION_ROLE_REFERENCE_INVALID")
        projected_roles[role_id] = role
    return {
        "functions": projected_functions,
        "roles": {name: projected_roles[name] for name in sorted(projected_roles)},
        "schema_version": 1,
    }


def lambda_configuration_sha256(template: dict[str, object]) -> str:
    model = lambda_configuration_model(template)
    return hashlib.sha256(canonical_json(model).encode("utf-8")).hexdigest()


def compare_lambda_configuration_sha256(
    template: dict[str, object],
    supplied: str | None,
) -> tuple[str, tuple[str, ...], str]:
    computed = lambda_configuration_sha256(template)
    if supplied is None or not supplied:
        return "BLOCKED", ("LAMBDA_CONFIGURATION_SHA256_REQUIRED",), computed
    if SHA256_PATTERN.fullmatch(supplied) is None:
        return "FAIL", ("LAMBDA_CONFIGURATION_SHA256_INVALID",), computed
    if supplied != computed:
        return "FAIL", ("LAMBDA_CONFIGURATION_SHA256_MISMATCH",), computed
    return "PASS", (), computed


def validate_structure(template: dict[str, object]) -> tuple[str, ...]:
    reasons: list[str] = []
    if not has_sam_transform(template):
        reasons.append("SAM_TRANSFORM_MISSING")
    for resource in resources_of_type(
        template,
        "AWS::Lambda::Function",
        "AWS::Serverless::Function",
    ).values():
        properties = resource.get("Properties", {})
        code_uri = properties.get("CodeUri")
        if isinstance(code_uri, str) and (
            Path(code_uri).is_absolute() or ".." in Path(code_uri).parts
        ):
            if code_uri != "../../dist/day15/aioa-lambda.zip":
                reasons.append("LAMBDA_CODE_URI_NOT_FROZEN_ARTIFACT")
        elif isinstance(code_uri, str) and code_uri != "../../dist/day15/aioa-lambda.zip":
            reasons.append("LAMBDA_CODE_URI_NOT_FROZEN_ARTIFACT")
        if properties.get("Runtime") != "python3.12":
            reasons.append("LAMBDA_RUNTIME_NOT_PYTHON_3_12")
        if properties.get("Architectures") != ["x86_64"]:
            reasons.append("LAMBDA_ARCHITECTURE_NOT_X86_64")
    return tuple(sorted(set(reasons)))


def _sam_validate(path: Path) -> tuple[str, tuple[str, ...]]:
    executable = shutil.which("sam")
    if executable is None:
        return "PARTIAL", ("SAM_CLI_UNAVAILABLE",)
    environment = {
        "AWS_CONFIG_FILE": os.devnull,
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "SAM_CLI_TELEMETRY": "0",
    }
    try:
        result = subprocess.run(
            (executable, "validate", "--lint", "--template-file", str(path)),
            cwd=ROOT,
            env=environment,
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "BLOCKED", ("SAM_VALIDATION_UNAVAILABLE",)
    if result.returncode != 0:
        return "FAIL", ("SAM_TEMPLATE_VALIDATION_FAILED",)
    return "PASS", ()


def validate_template(path: Path = DEFAULT_TEMPLATE) -> dict[str, object]:
    try:
        template = load_template(path)
        static_reasons = validate_structure(template)
    except TemplateFailure as error:
        return {
            "checks": [
                {"check_id": "D15-TEMPLATE-STATIC", "reasons": [error.reason], "status": "FAIL"},
                {
                    "check_id": "D15-TEMPLATE-SAM",
                    "reasons": ["STATIC_TEMPLATE_INVALID"],
                    "status": "BLOCKED",
                },
            ],
            "schema_version": 1,
            "status": "FAIL",
        }
    static_status = "FAIL" if static_reasons else "PASS"
    sam_status, sam_reasons = _sam_validate(path)
    overall = "FAIL" if static_status == "FAIL" or sam_status == "FAIL" else sam_status
    return {
        "checks": [
            {
                "check_id": "D15-TEMPLATE-STATIC",
                "reasons": list(static_reasons),
                "status": static_status,
            },
            {
                "check_id": "D15-TEMPLATE-SAM",
                "reasons": list(sam_reasons),
                "status": sam_status,
            },
        ],
        "schema_version": 1,
        "status": overall,
    }


def _exit_code(status: str) -> int:
    return {"PASS": 0, "FAIL": 1, "PARTIAL": 2, "BLOCKED": 3}.get(status, 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = validate_template(args.template)
    if args.json:
        print(canonical_json(payload))
    else:
        reasons = sorted(reason for check in payload["checks"] for reason in check["reasons"])
        print(f"DAY15_TEMPLATE {payload['status']} reasons={','.join(reasons) or '-'}")
    return _exit_code(str(payload["status"]))


if __name__ == "__main__":
    raise SystemExit(main())

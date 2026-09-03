"""W7 release-only packaging closure for the frozen W1-W6 product."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.build_public_submission import classify_path
from scripts.run_b5_container_gate import ContainerGateError
from scripts.run_w7_container_hero_gate import (
    _container_run_command,
    build_gate_receipt,
    validate_hero_result,
)
from scripts.w7_container_hero_client import _unexpected_tmp_changes

ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def test_image_packages_only_the_exact_w4_runtime_helper_closure() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert (
        "COPY scripts/w4_render_start_profile.py "
        "/app/scripts/w4_render_start_profile.py"
    ) in dockerfile
    assert "COPY scripts/w4_probe_site /app/scripts/w4_probe_site" in dockerfile
    assert (
        "COPY scripts/w7_container_hero_client.py "
        "/app/scripts/w7_container_hero_client.py"
    ) in dockerfile
    assert (
        "COPY scripts/w7_container_hero_supervisor.py "
        "/app/scripts/w7_container_hero_supervisor.py"
    ) in dockerfile
    assert "COPY scripts ./scripts" not in dockerfile
    assert "COPY scripts /app/scripts" not in dockerfile


def test_default_deny_build_context_reincludes_only_the_helper_closure() -> None:
    lines = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert lines[0].startswith("# Deny by default")
    assert lines[1] == "**"
    assert "!scripts/render_start.sh" in lines
    assert "!scripts/w4_render_start_profile.py" in lines
    assert "!scripts/w4_probe_site/" in lines
    assert "!scripts/w4_probe_site/*.py" in lines
    assert "!scripts/w7_container_hero_client.py" in lines
    assert "!scripts/w7_container_hero_supervisor.py" in lines
    assert "!scripts/**" not in lines


def test_packaged_helper_is_importable_from_gitless_app_shape(tmp_path: Path) -> None:
    app = tmp_path / "app"
    scripts = app / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/w4_render_start_profile.py", scripts)
    shutil.copytree(ROOT / "scripts/w4_probe_site", scripts / "w4_probe_site")
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": os.pathsep.join((str(app), str(ROOT / "src"))),
    }

    result = subprocess.run(
        (
            sys.executable,
            "-c",
            "from scripts.w4_render_start_profile import "
            "RenderStartContractV1Profile; assert RenderStartContractV1Profile",
        ),
        cwd=app,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0
    assert not (app / ".git").exists()


def test_container_start_contract_remains_cmd_based_and_render_compatible() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "ENTRYPOINT" not in dockerfile
    assert 'CMD ["python", "-m", "aioa_cloudops_agent.portable_server"]' in dockerfile
    assert "dockerCommand: /usr/local/bin/aioa-render-start" in (
        ROOT / "render.yaml"
    ).read_text(encoding="utf-8")


def test_external_deployment_and_dependency_inputs_are_unchanged_from_w6() -> None:
    assert _sha256("render.yaml") == (
        "c9e351188844ec4236068ffe62fa9747376ec520eabea39c9e92dd30909a645c"
    )
    assert _sha256("scripts/render_start.sh") == (
        "d350917c132a338605f630fde97a2ac017e1664fe9cf413a7153827326e6d250"
    )
    assert _sha256("requirements/build.lock") == (
        "d46492123b794c100b45c485f2981c1a12f71388f61439a5a662d850b19039a5"
    )
    assert _sha256("requirements/portable.lock") == (
        "a7be92862cb66b67f2bf5b664f62abee1dbd48d65e2ee12fbcbaa5be2dff5dcd"
    )
    assert _sha256("src/aioa_cloudops_agent/agent/factory.py") == (
        "4f1b02661a1effab421b3ec6ed506bf50a97c17ca5eb66cf959d201e0a881822"
    )


def test_public_bundle_marks_the_w4_helper_closure_as_required() -> None:
    for path in (
        "scripts/run_w7_container_hero_gate.py",
        "scripts/w4_render_start_profile.py",
        "scripts/w4_probe_site/__init__.py",
        "scripts/w4_probe_site/sitecustomize.py",
        "scripts/w7_container_hero_client.py",
        "scripts/w7_container_hero_supervisor.py",
    ):
        classification = classify_path(path)
        assert classification.included is True
        assert classification.name == "PUBLIC_REQUIRED"


def test_w4_helper_has_no_git_checkout_or_arbitrary_command_dependency() -> None:
    source = (ROOT / "scripts/w4_render_start_profile.py").read_text(encoding="utf-8")

    assert ".git" not in source
    assert "shell=True" not in source
    assert "os.system" not in source
    assert source.count("subprocess.Popen(") == 1
    assert "[sys.executable, *_PORTABLE_ARGV]" in source
    assert "cwd=root" in source


def test_release_packaging_does_not_change_frozen_runtime_authority() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "AIOA_MODEL_PROVIDER=mock" in dockerfile
    assert "AIOA_AWS_INTEGRATION_ENABLED=false" in dockerfile
    assert "AIOA_ALLOWED_EGRESS=none" in dockerfile
    assert "AIOA_AUTHORITY_MODE=HUMAN_APPROVAL_REQUIRED" in dockerfile
    assert "USER aioa" in dockerfile


def _hero_result() -> dict[str, object]:
    return {
        "approve": {
            "final_state": "SUCCESS_WITH_EVIDENCE",
            "patch_apply_count": 1,
            "replay_additional_mutations": 0,
            "replay_status": "REPLAY_REJECTED_RECONCILED",
        },
        "aws_calls": 0,
        "aws_mutations": 0,
        "bootstrap_secret_absent_from_server": True,
        "deny": {"final_state": "DENIED_BY_HUMAN", "mutation_count": 0},
        "external_network_connections": 0,
        "health": "PASS",
        "ready": "PASS",
        "server_argv_exact": True,
        "source_commit": "a" * 40,
        "status": "PASS",
        "token_file_mode": "0o600",
        "unexpected_file_mutations": 0,
    }


def test_w7_hero_gate_has_exact_networkless_render_start_contract() -> None:
    command = _container_run_command(
        "/safe/podman",
        "localhost/aioa:w7",
        ("--cgroups=disabled",),
        "0:0",
    )

    assert command[:2] == ("/safe/podman", "run")
    assert command[-3:] == (
        "localhost/aioa:w7",
        "-m",
        "scripts.w7_container_hero_supervisor",
    )
    assert command.count("none") == 1
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command
    assert command[command.index("--user") + 1] == "0:0"
    assert command[command.index("--entrypoint") + 1] == "python"
    assert not any("AWS_ACCESS_KEY" in value for value in command)


def test_w7_hero_result_is_exact_and_fail_closed() -> None:
    expected = _hero_result()

    assert validate_hero_result(expected, "a" * 40) == expected
    tampered = {**expected, "aws_calls": 1}
    try:
        validate_hero_result(tampered, "a" * 40)
    except ContainerGateError as error:
        assert error.reason == "W7_CONTAINER_HERO_RESULT_INVALID"
    else:
        raise AssertionError("unsafe hero receipt was accepted")


def test_w7_hero_gate_receipt_is_integrity_bound_and_sanitized() -> None:
    receipt = build_gate_receipt(
        image_reference="localhost/aioa:w7",
        image_contract={"id": "b" * 64, "source_commit": "a" * 40},
        nonroot_proof={"effective_uid": 65532, "token_mode": "0o600"},
        hero=_hero_result(),
        engine_user_override="0:0",
    )

    assert receipt["status"] == "PASS"
    assert receipt["external_network_connections"] == 0
    assert receipt["aws_mutations"] == 0
    assert receipt["container_start_command"] == "/usr/local/bin/aioa-render-start"
    assert receipt["certification_supervisor"] == (
        "scripts.w7_container_hero_supervisor"
    )
    assert len(str(receipt["receipt_sha256"])) == 64
    rendered = json.dumps(receipt)
    assert "w7-container-hero-synthetic" not in rendered


def test_w7_client_rejects_tmp_mutations_outside_fixed_workspace_roots() -> None:
    before = {
        "aioa-operator.token": ("file", 0o600, "a" * 64),
        "unrelated": ("file", 0o600, "b" * 64),
    }
    after = {
        "aioa-operator.token": ("file", 0o600, "a" * 64),
        "aioa-durable-truth-workspace-hero/run.json": ("file", 0o600, "c" * 64),
        "unrelated": ("file", 0o600, "d" * 64),
    }

    assert _unexpected_tmp_changes(before, after) == ("unrelated",)


def test_w7_supervisor_has_only_the_fixed_render_start_child() -> None:
    source = (ROOT / "scripts/w7_container_hero_supervisor.py").read_text(
        encoding="utf-8"
    )

    assert "from scripts.w7_container_hero_client import run_proof" in source
    assert '[_START_COMMAND]' in source
    assert '_START_COMMAND = "/usr/local/bin/aioa-render-start"' in source
    assert source.count("subprocess.Popen(") == 1
    assert "shell=True" not in source
    assert "exec(" not in source

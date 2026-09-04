"""Fail-closed unit proofs for the rootless Docker Phase 4 implementation."""

from __future__ import annotations

import hashlib
import inspect
import json
import tarfile
from io import BytesIO
from pathlib import Path

import pytest

from aioa_cloudops_agent.sandbox import (
    DOCKER_SANDBOX_V1,
    DockerCommandPlanBuilder,
    DockerSandboxProvider,
    DockerToolboxIdentity,
    SandboxPolicyDenied,
    docker_runtime,
    new_sandbox_ref,
)
from aioa_cloudops_agent.sandbox import provider as provider_module
from aioa_cloudops_agent.sandbox.docker_runtime import DockerCli, DockerCliResult

SOURCE_COMMIT = "1" * 40
IMAGE_DIGEST = "2" * 64


def _toolbox() -> DockerToolboxIdentity:
    return DockerToolboxIdentity(
        image_reference=f"sha256:{IMAGE_DIGEST}",
        image_digest=IMAGE_DIGEST,
        source_commit=SOURCE_COMMIT,
    )


def _result(stdout: bytes = b"", *, returncode: int = 0) -> DockerCliResult:
    return DockerCliResult(
        returncode=returncode,
        stdout=stdout,
        stderr=b"",
        duration_milliseconds=1,
        output_truncated=False,
    )


def test_docker_transport_has_fixed_rootless_environment_and_no_shell_surface() -> None:
    client = DockerCli("/usr/bin/docker", operator_uid=1234)

    assert client._environment == {
        "DOCKER_HOST": "unix:///run/user/1234/docker.sock",
        "LANG": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
    }
    source = inspect.getsource(docker_runtime)
    assert "subprocess" not in source
    assert "shell=True" not in source
    assert "os.system" not in source


def test_docker_transport_rejects_root_and_unbounded_inputs_before_spawn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="non-root"):
        DockerCli("/usr/bin/docker", operator_uid=0)

    client = DockerCli("/usr/bin/docker", operator_uid=1234)

    def unexpected_spawn(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("invalid input reached the process boundary")

    monkeypatch.setattr(docker_runtime.OwnedProcess, "spawn", unexpected_spawn)
    for argv in ((), ("run\nunsafe",), tuple("x" for _ in range(97))):
        with pytest.raises(ValueError, match="argv"):
            client.run(argv)
    with pytest.raises(ValueError, match="stdin"):
        client.run(("run",), stdin=b"x" * (20 * 1024 * 1024 + 1))


def test_command_builder_exposes_only_fixed_internal_operations() -> None:
    builder = DockerCommandPlanBuilder("/usr/bin/docker", _toolbox(), DOCKER_SANDBOX_V1)
    reference = new_sandbox_ref(DOCKER_SANDBOX_V1)

    assert not hasattr(builder, "internal")
    plans = (
        builder.package_manager_version(reference, "PYTHON"),
        builder.package_manager_version(reference, "NODE"),
        builder.read_file(reference, "src/demo.py"),
        builder.atomic_write(reference, "src/demo.py"),
        builder.workspace_probe(reference, "working"),
        builder.runtime_probe(reference),
    )
    for plan in plans:
        rendered = " ".join(plan.argv)
        assert "--network=none" in plan.argv
        assert "--read-only" in plan.argv
        assert "--cap-drop=ALL" in plan.argv
        assert "--security-opt=no-new-privileges:true" in plan.argv
        assert "--user=65532:65532" in plan.argv
        assert "/home/" not in rendered
        assert "docker.sock" not in rendered
    with pytest.raises(ValueError):
        builder.read_file(reference, "../escape")


def test_staging_archive_is_deterministic_owned_and_excludes_authority(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    nested = source / "src"
    nested.mkdir(parents=True)
    (source / "README.md").write_text("fixture\n", encoding="utf-8")
    (nested / "demo.py").write_text("VALUE = 1\n", encoding="utf-8")

    first, first_records = provider_module._build_staging_archive(source)
    second, second_records = provider_module._build_staging_archive(source)

    assert first == second
    assert first_records == second_records
    with tarfile.open(fileobj=BytesIO(first), mode="r:") as archive:
        members = archive.getmembers()
    assert members
    assert all(member.uid == 65532 and member.gid == 65532 for member in members)
    assert all(member.mtime == 0 and member.name != ".git" for member in members)

    (source / ".git").mkdir()
    with pytest.raises(SandboxPolicyDenied, match="GIT_AUTHORITY_DENIED"):
        provider_module._build_staging_archive(source)


def test_staging_archive_rejects_links_hardlinks_and_secret_paths(tmp_path: Path) -> None:
    linked = tmp_path / "linked"
    linked.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("outside\n", encoding="utf-8")
    (linked / "escape").symlink_to(outside)
    with pytest.raises(SandboxPolicyDenied, match="LINK_DENIED"):
        provider_module._build_staging_archive(linked)

    hardlinked = tmp_path / "hardlinked"
    hardlinked.mkdir()
    original = hardlinked / "one"
    original.write_text("same\n", encoding="utf-8")
    (hardlinked / "two").hardlink_to(original)
    with pytest.raises(SandboxPolicyDenied, match="FILE_TYPE_DENIED"):
        provider_module._build_staging_archive(hardlinked)

    secret = tmp_path / "secret"
    secret.mkdir()
    (secret / ".env").write_text("synthetic=true\n", encoding="utf-8")
    with pytest.raises(SandboxPolicyDenied, match="SECRET_PATH_DENIED"):
        provider_module._build_staging_archive(secret)


def test_workspace_probe_records_are_digest_bound_and_ordered() -> None:
    records = [["a.txt", "a" * 64, 0o644], ["src/b.py", "b" * 64, 0o600]]
    encoded = json.dumps(records, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    payload: dict[str, object] = {
        "file_count": 2,
        "records": records,
        "total_bytes": 9,
        "tree_sha256": hashlib.sha256(encoded).hexdigest(),
    }

    assert provider_module._records_from_probe(payload) == {
        "a.txt": ("a" * 64, 0o644),
        "src/b.py": ("b" * 64, 0o600),
    }
    payload["records"] = list(reversed(records))
    with pytest.raises(Exception, match="ORDER_INVALID"):
        provider_module._records_from_probe(payload)


def test_provider_certifies_exact_rootless_image_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = tmp_path / "docker"
    engine.write_bytes(b"fixed test executable\n")
    engine.chmod(0o700)

    class FakeDockerCli:
        def __init__(self, engine_path: str) -> None:
            assert engine_path == engine.as_posix()

        def checked(self, argv: tuple[str, ...], **_kwargs: object) -> DockerCliResult:
            if argv[0] == "version":
                return _result(b"29.8.0\n")
            if argv[0] == "info":
                return _result(b'["name=rootless"]')
            assert argv == ("image", "inspect", f"sha256:{IMAGE_DIGEST}")
            return _result(
                json.dumps(
                    [
                        {
                            "Config": {
                                "Labels": {
                                    "dev.aioa.sandbox.policy": "DOCKER_SANDBOX_V1",
                                    "org.opencontainers.image.revision": SOURCE_COMMIT,
                                },
                                "User": "65532:65532",
                                "WorkingDir": "/workspace",
                            },
                            "Id": f"sha256:{IMAGE_DIGEST}",
                        }
                    ]
                ).encode("utf-8")
            )

    monkeypatch.setattr(provider_module, "DockerCli", FakeDockerCli)

    available = DockerSandboxProvider(engine.as_posix(), toolbox=_toolbox()).availability()

    assert available.available is True
    assert available.status == "AVAILABLE"


def test_provider_rejects_image_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = tmp_path / "docker"
    engine.write_bytes(b"fixed test executable\n")
    engine.chmod(0o700)

    class WrongImageDockerCli:
        def __init__(self, _engine_path: str) -> None:
            pass

        def checked(self, argv: tuple[str, ...], **_kwargs: object) -> DockerCliResult:
            if argv[0] == "version":
                return _result(b"29.8.0\n")
            if argv[0] == "info":
                return _result(b'["name=rootless"]')
            return _result(
                json.dumps(
                    [
                        {
                            "Config": {
                                "Labels": {},
                                "User": "0:0",
                                "WorkingDir": "/",
                            },
                            "Id": f"sha256:{IMAGE_DIGEST}",
                        }
                    ]
                ).encode("utf-8")
            )

    monkeypatch.setattr(provider_module, "DockerCli", WrongImageDockerCli)

    unavailable = DockerSandboxProvider(engine.as_posix(), toolbox=_toolbox()).availability()

    assert unavailable.available is False
    assert unavailable.status == "DOCKER_DAEMON_UNPROVEN"

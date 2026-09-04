"""Unit proofs for the value-free W7A toolbox privacy scanner."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from scripts.scan_w7a_toolbox_export import ToolboxScanError, scan_rootfs

IMAGE_SHA256 = "a" * 64
SOURCE_COMMIT = "b" * 40
SIX_SHA256 = "4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274"


def _rootfs(root: Path) -> Path:
    binary = root / "usr/local/bin"
    python_cache = root / "opt/aioa-cache/python"
    npm_cache = root / "opt/aioa-cache/npm"
    binary.mkdir(parents=True)
    python_cache.mkdir(parents=True)
    npm_cache.mkdir(parents=True)
    for name in ("atomic-write", "read-file", "runtime-probe", "workspace-probe"):
        path = binary / f"aioa-{name}"
        path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        path.chmod(0o555)
    # A tiny deterministic stand-in is written, then the hash check is monkeypatched below.
    (python_cache / "six-1.17.0-py2.py3-none-any.whl").write_bytes(b"wheel")
    (npm_cache / "index").write_bytes(
        b"sha512-41Cifkg6e8TylSpdtTpeLVMqvSBEVzTttHvERD741+pnZ8ANv0004MRL43QKPDlK9cGv"
        b"Np6NZWZUBlbGXYxxng=="
    )
    return root


def test_toolbox_scan_is_value_free_and_detects_no_fixture_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rootfs = _rootfs(tmp_path / "rootfs")
    original = hashlib.sha256

    class FixtureDigest:
        def __init__(self, value: bytes = b"") -> None:
            self._value = value

        def hexdigest(self) -> str:
            if self._value == b"wheel":
                return SIX_SHA256
            return original(self._value).hexdigest()

    monkeypatch.setattr("scripts.scan_w7a_toolbox_export.hashlib.sha256", FixtureDigest)

    receipt = scan_rootfs(
        rootfs,
        image_sha256=IMAGE_SHA256,
        source_commit=SOURCE_COMMIT,
    )

    assert receipt["status"] == "PASS"
    assert receipt["findings"] == []
    assert receipt["aws_mutations"] == 0


def test_toolbox_scan_reports_reason_not_secret_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rootfs = _rootfs(tmp_path / "rootfs")
    secret = "ghp_" + "A" * 40
    (rootfs / "leak.txt").write_text(secret, encoding="utf-8")
    monkeypatch.setattr(
        "scripts.scan_w7a_toolbox_export.hashlib.sha256",
        lambda value=b"": type(
            "Digest",
            (),
            {"hexdigest": lambda self: SIX_SHA256 if value == b"wheel" else "c" * 64},
        )(),
    )

    receipt = scan_rootfs(
        rootfs,
        image_sha256=IMAGE_SHA256,
        source_commit=SOURCE_COMMIT,
    )

    assert receipt["status"] == "FAIL"
    assert receipt["findings"] == [{"path": "leak.txt", "reason": "GITHUB_TOKEN"}]
    assert secret not in str(receipt)


def test_toolbox_scan_rejects_invalid_identity(tmp_path: Path) -> None:
    with pytest.raises(ToolboxScanError, match="INPUT_INVALID"):
        scan_rootfs(tmp_path, image_sha256="latest", source_commit=SOURCE_COMMIT)

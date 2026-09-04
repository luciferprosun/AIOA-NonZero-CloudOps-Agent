#!/usr/bin/env python3
"""Scan an exact exported W7A toolbox rootfs without printing matched values."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from collections.abc import Iterator, Sequence
from pathlib import Path, PurePosixPath
from typing import Final

_DIGEST: Final = re.compile(r"^[0-9a-f]{64}$")
_COMMIT: Final = re.compile(r"^[0-9a-f]{40}$")
_AWS_ACCESS_KEY: Final = re.compile(rb"(?:AKIA|ASIA)[0-9A-Z]{16}")
_AWS_SECRET: Final = re.compile(rb"(?i)aws_secret_access_key\s*[=:]\s*['\"]?([A-Za-z0-9/+=]{20,})")
_GITHUB_TOKEN: Final = re.compile(
    rb"(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{50,255})"
)
_OPENAI_TOKEN: Final = re.compile(rb"sk-(?:proj-)?[A-Za-z0-9_-]{32,255}")
_PRIVATE_KEY: Final = re.compile(
    rb"-----BEGIN (?P<kind>(?:RSA |EC |OPENSSH )?PRIVATE KEY)-----\r?\n"
    rb"(?:[A-Za-z0-9+/=]{32,}\r?\n){2,}"
    rb"-----END (?P=kind)-----"
)
_SIX_SHA256: Final = "4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274"
_NPM_INTEGRITY: Final = (
    b"sha512-41Cifkg6e8TylSpdtTpeLVMqvSBEVzTttHvERD741+pnZ8ANv0004MRL43QKPDlK9cGv"
    b"Np6NZWZUBlbGXYxxng=="
)


class ToolboxScanError(RuntimeError):
    """Stable value-free toolbox scan failure."""


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _regular_files(rootfs: Path) -> Iterator[tuple[PurePosixPath, Path, int]]:
    for directory, names, filenames in os.walk(rootfs, topdown=True, followlinks=False):
        names[:] = sorted(name for name in names if not (Path(directory) / name).is_symlink())
        for name in sorted(filenames):
            path = Path(directory) / name
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                continue
            if stat.S_ISREG(metadata.st_mode):
                yield PurePosixPath(path.relative_to(rootfs).as_posix()), path, metadata.st_size


def _path_reason(relative: PurePosixPath) -> str | None:
    parts = tuple(part.casefold() for part in relative.parts)
    name = parts[-1]
    if ".git" in parts:
        return "GIT_METADATA"
    if name == ".env" or name.startswith(".env."):
        return "ENV_FILE"
    if ".aws" in parts and name in {"config", "credentials"}:
        return "AWS_CREDENTIAL_FILE"
    if name in {".git-credentials", ".netrc", "operator.token"}:
        return "CREDENTIAL_FILE"
    if relative.suffix.casefold() in {".key", ".p12", ".pfx"}:
        return "PRIVATE_KEY_FILE"
    return None


def _content_reasons(path: Path) -> tuple[str, ...]:
    findings: set[str] = set()
    overlap = b""
    binary = False
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            sample = overlap + chunk
            binary = binary or b"\0" in chunk
            patterns = [
                ("GITHUB_TOKEN", _GITHUB_TOKEN),
                ("OPENAI_TOKEN", _OPENAI_TOKEN),
                ("PRIVATE_KEY_MATERIAL", _PRIVATE_KEY),
            ]
            if not binary:
                patterns.extend(
                    (
                        ("AWS_ACCESS_KEY", _AWS_ACCESS_KEY),
                        ("AWS_SECRET_VALUE", _AWS_SECRET),
                    )
                )
            for reason, pattern in patterns:
                if pattern.search(sample) is not None:
                    findings.add(reason)
            overlap = sample[-4096:]
    return tuple(sorted(findings))


def scan_rootfs(rootfs: Path, *, image_sha256: str, source_commit: str) -> dict[str, object]:
    """Return a deterministic, matched-value-free privacy receipt."""

    if (
        not rootfs.is_absolute()
        or rootfs == Path("/")
        or rootfs.is_symlink()
        or not rootfs.is_dir()
        or _DIGEST.fullmatch(image_sha256) is None
        or _COMMIT.fullmatch(source_commit) is None
    ):
        raise ToolboxScanError("W7A_TOOLBOX_SCAN_INPUT_INVALID")
    required = {
        "atomic_write": rootfs / "usr/local/bin/aioa-atomic-write",
        "read_file": rootfs / "usr/local/bin/aioa-read-file",
        "runtime_probe": rootfs / "usr/local/bin/aioa-runtime-probe",
        "workspace_probe": rootfs / "usr/local/bin/aioa-workspace-probe",
    }
    if any(not path.is_file() or path.is_symlink() for path in required.values()):
        raise ToolboxScanError("W7A_TOOLBOX_ROOTFS_CONTRACT_INVALID")
    wheel = rootfs / "opt/aioa-cache/python/six-1.17.0-py2.py3-none-any.whl"
    if not wheel.is_file() or hashlib.sha256(wheel.read_bytes()).hexdigest() != _SIX_SHA256:
        raise ToolboxScanError("W7A_TOOLBOX_PYTHON_CACHE_IDENTITY_INVALID")

    findings: list[dict[str, str]] = []
    regular_files = 0
    scanned_bytes = 0
    npm_integrity_found = False
    for relative, path, size in _regular_files(rootfs):
        regular_files += 1
        scanned_bytes += size
        reason = _path_reason(relative)
        if reason is not None:
            findings.append({"path": relative.as_posix(), "reason": reason})
        for content_reason in _content_reasons(path):
            findings.append({"path": relative.as_posix(), "reason": content_reason})
        if relative.parts[:3] == ("opt", "aioa-cache", "npm") and not npm_integrity_found:
            with path.open("rb") as stream:
                npm_integrity_found = _NPM_INTEGRITY in stream.read(2 * 1024 * 1024)

    findings.sort(key=lambda item: (item["path"], item["reason"]))
    executable_modes = {
        name: stat.S_IMODE(path.stat().st_mode) for name, path in sorted(required.items())
    }
    material: dict[str, object] = {
        "aws_calls": 0,
        "aws_mutations": 0,
        "checks": {
            "credential_material_absent": not findings,
            "npm_cache_integrity_bound": npm_integrity_found,
            "python_cache_hash_bound": True,
            "toolbox_executables_mode_0555": all(
                mode == 0o555 for mode in executable_modes.values()
            ),
        },
        "external_deployments": 0,
        "findings": findings,
        "findings_count": len(findings),
        "image_sha256": image_sha256,
        "regular_files_scanned": regular_files,
        "remote_pushes": 0,
        "receipt_type": "AIOA_W7A_TOOLBOX_EXPORT_PRIVACY_SCAN",
        "scanned_bytes": scanned_bytes,
        "schema_version": 1,
        "source_commit": source_commit,
        "status": (
            "PASS"
            if not findings
            and npm_integrity_found
            and all(mode == 0o555 for mode in executable_modes.values())
            else "FAIL"
        ),
    }
    return {**material, "receipt_sha256": hashlib.sha256(_canonical_bytes(material)).hexdigest()}


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rootfs", type=Path, required=True)
    parser.add_argument("--image-sha256", required=True)
    parser.add_argument("--source-commit", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _arguments(argv)
    try:
        receipt = scan_rootfs(
            arguments.rootfs.resolve(strict=True),
            image_sha256=arguments.image_sha256,
            source_commit=arguments.source_commit,
        )
    except (OSError, ToolboxScanError) as error:
        print(
            json.dumps(
                {
                    "aws_mutations": 0,
                    "reason": str(error),
                    "remote_pushes": 0,
                    "status": "FAIL",
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

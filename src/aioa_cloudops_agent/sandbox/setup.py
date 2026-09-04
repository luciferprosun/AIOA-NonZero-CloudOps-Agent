"""Deterministic manifest-to-argv setup planner for disposable sandboxes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tomllib
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import cast

from aioa_cloudops_agent.agent import digest_workspace_tree

from .contracts import (
    RepositorySourceIdentity,
    SetupEcosystem,
    SetupManifest,
    SetupPlan,
)

_REQUIREMENT = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[A-Za-z0-9_,.-]+\])?"
    r"==[A-Za-z0-9][A-Za-z0-9.!+_-]*"
    r"(?:[ \t]+--hash=sha256:[0-9a-f]{64})+$"
)
_URL = re.compile(r"https?://[^\s\"']+", flags=re.IGNORECASE)
_ALLOWED_PYTHON_URL_PREFIXES = (
    "https://files.pythonhosted.org/",
    "https://pypi.org/",
)
_ALLOWED_NPM_URL_PREFIX = "https://registry.npmjs.org/"


class SetupPlannerError(ValueError):
    """Stable fail-closed setup decision that never includes host paths or content."""


class DeterministicSetupPlanner:
    """Create fixed install argv from content-bound lock/manifest evidence."""

    def inspect_repository(
        self,
        root: Path,
        *,
        source_commit: str | None = None,
    ) -> RepositorySourceIdentity:
        tree_sha256 = digest_workspace_tree(root)
        file_count = 0
        total_bytes = 0
        for candidate in sorted(root.rglob("*")):
            metadata = candidate.lstat()
            if stat.S_ISDIR(metadata.st_mode):
                continue
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise SetupPlannerError("SETUP_REPOSITORY_FILE_TYPE_FORBIDDEN")
            file_count += 1
            total_bytes += metadata.st_size
        return RepositorySourceIdentity(
            tree_sha256=tree_sha256,
            source_commit=source_commit,
            file_count=file_count,
            total_bytes=total_bytes,
        )

    def plan_python(self, root: Path, expected_tree_sha256: str) -> SetupPlan:
        self._verify_tree(root, expected_tree_sha256)
        has_requirements = _regular_path(root, "requirements.txt")
        has_pyproject = _regular_path(root, "pyproject.toml")
        has_uv_lock = _regular_path(root, "uv.lock")
        if has_requirements and (has_pyproject or has_uv_lock):
            raise SetupPlannerError("PYTHON_SETUP_CONTRACT_AMBIGUOUS")
        if has_pyproject != has_uv_lock:
            raise SetupPlannerError("PYTHON_UV_LOCK_PAIR_INCOMPLETE")
        if has_requirements:
            manifests, contents = self._read_manifest_set(
                root,
                expected_tree_sha256,
                ("requirements.txt",),
            )
            _validate_requirements(contents[0])
            return SetupPlan.build(
                expected_tree_sha256,
                SetupEcosystem.PYTHON_REQUIREMENTS,
                manifests,
            )
        if has_pyproject and has_uv_lock:
            manifests, contents = self._read_manifest_set(
                root,
                expected_tree_sha256,
                ("pyproject.toml", "uv.lock"),
            )
            _validate_uv_inputs(contents[0], contents[1])
            return SetupPlan.build(expected_tree_sha256, SetupEcosystem.PYTHON_UV, manifests)
        raise SetupPlannerError("PYTHON_LOCKED_SETUP_EVIDENCE_MISSING")

    def plan_node(self, root: Path, expected_tree_sha256: str) -> SetupPlan:
        self._verify_tree(root, expected_tree_sha256)
        if (root / ".npmrc").exists():
            raise SetupPlannerError("NPM_PROJECT_CONFIG_DENIED")
        if not _regular_path(root, "package.json") or not _regular_path(root, "package-lock.json"):
            raise SetupPlannerError("NODE_PACKAGE_LOCK_PAIR_MISSING")
        manifests, contents = self._read_manifest_set(
            root,
            expected_tree_sha256,
            ("package-lock.json", "package.json"),
        )
        _validate_npm_inputs(lock_raw=contents[0], package_raw=contents[1])
        return SetupPlan.build(expected_tree_sha256, SetupEcosystem.NODE_NPM, manifests)

    @staticmethod
    def _verify_tree(root: Path, expected_tree_sha256: str) -> None:
        try:
            observed = digest_workspace_tree(root)
        except (OSError, ValueError) as error:
            raise SetupPlannerError("SETUP_REPOSITORY_IDENTITY_INVALID") from error
        if observed != expected_tree_sha256:
            raise SetupPlannerError("SETUP_REPOSITORY_IDENTITY_MISMATCH")

    def _read_manifest_set(
        self,
        root: Path,
        expected_tree_sha256: str,
        relative_paths: tuple[str, ...],
    ) -> tuple[tuple[SetupManifest, ...], tuple[bytes, ...]]:
        contents = tuple(_secure_read(root, path) for path in relative_paths)
        self._verify_tree(root, expected_tree_sha256)
        manifests = tuple(
            SetupManifest(
                relative_path=path,
                sha256=hashlib.sha256(content).hexdigest(),
                size=len(content),
            )
            for path, content in zip(relative_paths, contents, strict=True)
        )
        return manifests, contents


def _regular_path(root: Path, relative_path: str) -> bool:
    candidate = root / relative_path
    try:
        metadata = candidate.lstat()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise SetupPlannerError("SETUP_MANIFEST_STAT_FAILED") from error
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise SetupPlannerError("SETUP_MANIFEST_FILE_TYPE_FORBIDDEN")
    return True


def _secure_read(root: Path, relative_path: str) -> bytes:
    """Read one fixed known manifest through no-follow directory descriptors."""

    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    directory_flags = flags | getattr(os, "O_DIRECTORY", 0)
    descriptors: list[int] = []
    try:
        current = os.open(root, directory_flags)
        descriptors.append(current)
        parts = Path(relative_path).parts
        for part in parts[:-1]:
            current = os.open(part, directory_flags, dir_fd=current)
            descriptors.append(current)
        file_descriptor = os.open(parts[-1], flags, dir_fd=current)
        descriptors.append(file_descriptor)
        before = os.fstat(file_descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size <= 0
            or before.st_size > 1024 * 1024
        ):
            raise SetupPlannerError("SETUP_MANIFEST_FILE_INVALID")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(file_descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise SetupPlannerError("SETUP_MANIFEST_SHORT_READ")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(file_descriptor, 1):
            raise SetupPlannerError("SETUP_MANIFEST_GREW_DURING_READ")
        after = os.fstat(file_descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise SetupPlannerError("SETUP_MANIFEST_CHANGED_DURING_READ")
        return b"".join(chunks)
    except SetupPlannerError:
        raise
    except OSError as error:
        raise SetupPlannerError("SETUP_MANIFEST_SECURE_READ_FAILED") from error
    finally:
        for descriptor in reversed(descriptors):
            with suppress(OSError):
                os.close(descriptor)


def _text(raw: bytes, code: str) -> str:
    try:
        value = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SetupPlannerError(code) from error
    if "\x00" in value or value.startswith("\ufeff"):
        raise SetupPlannerError(code)
    return value


def _validate_requirements(raw: bytes) -> None:
    value = _text(raw, "PYTHON_REQUIREMENTS_ENCODING_INVALID")
    requirements = 0
    for line in value.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        requirements += 1
        if _REQUIREMENT.fullmatch(stripped) is None:
            raise SetupPlannerError("PYTHON_REQUIREMENT_NOT_EXACT_HASH_PIN")
    if requirements == 0:
        raise SetupPlannerError("PYTHON_REQUIREMENTS_EMPTY")


def _validate_uv_inputs(pyproject_raw: bytes, lock_raw: bytes) -> None:
    pyproject_text = _text(pyproject_raw, "PYPROJECT_ENCODING_INVALID")
    lock_text = _text(lock_raw, "UV_LOCK_ENCODING_INVALID")
    try:
        pyproject = tomllib.loads(pyproject_text)
        lock = tomllib.loads(lock_text)
    except tomllib.TOMLDecodeError as error:
        raise SetupPlannerError("PYTHON_UV_INPUT_INVALID") from error
    if not isinstance(pyproject, dict) or not isinstance(lock, dict):
        raise SetupPlannerError("PYTHON_UV_INPUT_INVALID")
    if "project" not in pyproject or "version" not in lock:
        raise SetupPlannerError("PYTHON_UV_INPUT_INCOMPLETE")
    for text in (pyproject_text, lock_text):
        lowered = text.casefold()
        if "index-url" in lowered or "extra-index-url" in lowered:
            raise SetupPlannerError("PYTHON_CUSTOM_REGISTRY_DENIED")
        for url in _URL.findall(text):
            if not url.startswith(_ALLOWED_PYTHON_URL_PREFIXES):
                raise SetupPlannerError("PYTHON_CUSTOM_REGISTRY_DENIED")


def _validate_npm_inputs(*, lock_raw: bytes, package_raw: bytes) -> None:
    try:
        lock = json.loads(_text(lock_raw, "NPM_LOCK_ENCODING_INVALID"))
        package = json.loads(_text(package_raw, "NPM_PACKAGE_ENCODING_INVALID"))
    except json.JSONDecodeError as error:
        raise SetupPlannerError("NPM_MANIFEST_JSON_INVALID") from error
    if not isinstance(lock, dict) or not isinstance(package, dict):
        raise SetupPlannerError("NPM_MANIFEST_JSON_INVALID")
    if lock.get("lockfileVersion") not in {2, 3}:
        raise SetupPlannerError("NPM_LOCK_VERSION_UNSUPPORTED")
    if not isinstance(lock.get("packages"), dict):
        raise SetupPlannerError("NPM_LOCK_PACKAGES_MISSING")
    if lock.get("name") != package.get("name") or lock.get("version") != package.get("version"):
        raise SetupPlannerError("NPM_LOCK_PACKAGE_IDENTITY_MISMATCH")
    _validate_npm_registry(cast(Mapping[str, object], lock))
    _validate_npm_dependency_urls(cast(Mapping[str, object], package))


def _validate_npm_registry(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "resolved" and isinstance(child, str):
                if not child.startswith(_ALLOWED_NPM_URL_PREFIX):
                    raise SetupPlannerError("NPM_CUSTOM_REGISTRY_DENIED")
            else:
                _validate_npm_registry(child)
    elif isinstance(value, list):
        for child in value:
            _validate_npm_registry(child)


def _validate_npm_dependency_urls(value: object) -> None:
    if isinstance(value, dict):
        for child in value.values():
            _validate_npm_dependency_urls(child)
    elif isinstance(value, list):
        for child in value:
            _validate_npm_dependency_urls(child)
    elif (
        isinstance(value, str)
        and ("://" in value or value.startswith(("git+", "file:")))
        and not value.startswith(_ALLOWED_NPM_URL_PREFIX)
    ):
        raise SetupPlannerError("NPM_CUSTOM_REGISTRY_DENIED")

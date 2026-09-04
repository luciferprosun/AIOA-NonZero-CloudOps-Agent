#!/usr/bin/env python3
"""Emit a bounded content identity for an AIOA-owned sandbox workspace."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from pathlib import Path

ROOT = Path("/workspace")
MAX_FILES = 256
MAX_BYTES = 16 * 1024 * 1024
SETUP_ROOTS = frozenset({".aioa-python", "node_modules"})
SECRET_ROOTS = frozenset({".aws", ".ssh"})
SECRET_NAMES = frozenset({".env", "credentials"})
SENSITIVE_ENV_PARTS = (
    "AWS",
    "AZURE",
    "CREDENTIAL",
    "GCP",
    "GH_",
    "GITHUB",
    "KEY",
    "OPENAI",
    "PASSWORD",
    "SECRET",
    "SSH",
    "TOKEN",
)


def _included(relative: str, mode: str) -> bool:
    first = relative.split("/", 1)[0]
    if mode == "working":
        return first not in SETUP_ROOTS
    if mode == "setup":
        return first in SETUP_ROOTS
    return True


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"source", "working", "setup"}:
        raise SystemExit("usage: aioa-workspace-probe source|working|setup")
    mode = sys.argv[1]
    records: list[tuple[str, str, int]] = []
    total_bytes = 0
    for candidate in sorted(ROOT.rglob("*")):
        relative = candidate.relative_to(ROOT).as_posix()
        if not _included(relative, mode):
            continue
        metadata = candidate.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise SystemExit("WORKSPACE_LINK_FORBIDDEN")
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise SystemExit("WORKSPACE_FILE_TYPE_FORBIDDEN")
        first = relative.split("/", 1)[0]
        if first in SECRET_ROOTS or Path(relative).name in SECRET_NAMES:
            raise SystemExit("WORKSPACE_SECRET_PATH_FORBIDDEN")
        content = candidate.read_bytes()
        total_bytes += len(content)
        if len(records) >= MAX_FILES or total_bytes > MAX_BYTES:
            raise SystemExit("WORKSPACE_SIZE_LIMIT_EXCEEDED")
        records.append(
            (
                relative,
                hashlib.sha256(content).hexdigest(),
                metadata.st_mode & 0o777,
            )
        )
    encoded = json.dumps(records, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    result = {
        "file_count": len(records),
        "records": records,
        "mode": mode,
        "sensitive_environment_names": sorted(
            name
            for name in os.environ
            if any(marker in name.upper() for marker in SENSITIVE_ENV_PARTS)
        ),
        "total_bytes": total_bytes,
        "tree_sha256": hashlib.sha256(encoded).hexdigest(),
        "uid": os.getuid(),
        "gid": os.getgid(),
    }
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

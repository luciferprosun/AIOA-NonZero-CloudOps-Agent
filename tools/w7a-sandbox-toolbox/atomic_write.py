#!/usr/bin/env python3
"""Apply one bounded atomic write below /workspace without following links."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from contextlib import suppress
from pathlib import PurePosixPath

MAX_BYTES = 16 * 1024 * 1024
ROOT = "/workspace"


def _parts(value: str) -> tuple[str, ...]:
    candidate = PurePosixPath(value)
    if (
        not value
        or value != value.strip()
        or candidate.is_absolute()
        or candidate.as_posix() != value
        or len(value) > 1024
    ):
        raise SystemExit("SANDBOX_WRITE_PATH_INVALID")
    if any(part in {"", ".", ".."} or part.startswith(".") for part in candidate.parts):
        raise SystemExit("SANDBOX_WRITE_PATH_INVALID")
    return candidate.parts


def _read_input() -> bytes:
    content = sys.stdin.buffer.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise SystemExit("SANDBOX_WRITE_SIZE_EXCEEDED")
    return content


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: aioa-atomic-write RELATIVE_PATH")
    parts = _parts(sys.argv[1])
    content = _read_input()
    directory_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors: list[int] = []
    temporary = f".aioa-write-{os.getpid()}"
    current: int | None = None
    try:
        current = os.open(ROOT, directory_flags)
        descriptors.append(current)
        for part in parts[:-1]:
            current = os.open(part, directory_flags, dir_fd=current)
            descriptors.append(current)
        previous_sha256 = None
        try:
            existing = os.open(
                parts[-1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=current
            )
        except FileNotFoundError:
            pass
        else:
            descriptors.append(existing)
            metadata = os.fstat(existing)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise SystemExit("SANDBOX_WRITE_TARGET_INVALID")
            digest = hashlib.sha256()
            observed = 0
            while chunk := os.read(existing, min(64 * 1024, MAX_BYTES + 1 - observed)):
                observed += len(chunk)
                if observed > MAX_BYTES:
                    raise SystemExit("SANDBOX_WRITE_TARGET_SIZE_EXCEEDED")
                digest.update(chunk)
            previous_sha256 = digest.hexdigest()
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
            dir_fd=current,
        )
        descriptors.append(descriptor)
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o644)
        os.replace(temporary, parts[-1], src_dir_fd=current, dst_dir_fd=current)
        os.fsync(current)
    finally:
        if current is not None:
            with suppress(FileNotFoundError, OSError):
                os.unlink(temporary, dir_fd=current)
        for descriptor in reversed(descriptors):
            with suppress(OSError):
                os.close(descriptor)
    result = {
        "previous_sha256": previous_sha256,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
    }
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

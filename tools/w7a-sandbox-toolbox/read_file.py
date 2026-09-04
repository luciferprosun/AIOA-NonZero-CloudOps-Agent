#!/usr/bin/env python3
"""Read one bounded regular file below /workspace without following links."""

from __future__ import annotations

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
        or any(part in {"", ".", ".."} or part.startswith(".") for part in candidate.parts)
    ):
        raise SystemExit("SANDBOX_READ_PATH_INVALID")
    return candidate.parts


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: aioa-read-file RELATIVE_PATH")
    parts = _parts(sys.argv[1])
    file_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    directory_flags = file_flags | os.O_DIRECTORY
    descriptors: list[int] = []
    try:
        current = os.open(ROOT, directory_flags)
        descriptors.append(current)
        for part in parts[:-1]:
            current = os.open(part, directory_flags, dir_fd=current)
            descriptors.append(current)
        descriptor = os.open(parts[-1], file_flags, dir_fd=current)
        descriptors.append(descriptor)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_BYTES:
            raise SystemExit("SANDBOX_READ_TARGET_INVALID")
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                raise SystemExit("SANDBOX_READ_SHORT")
            sys.stdout.buffer.write(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise SystemExit("SANDBOX_READ_TARGET_GREW")
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise SystemExit("SANDBOX_READ_TARGET_DRIFT")
    finally:
        for descriptor in reversed(descriptors):
            with suppress(OSError):
                os.close(descriptor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

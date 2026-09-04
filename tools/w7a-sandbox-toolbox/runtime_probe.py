#!/usr/bin/env python3
"""Report value-free runtime isolation facts from inside the sandbox."""

from __future__ import annotations

import json
import os
import resource
import socket
from pathlib import Path

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


def _status_value(name: str) -> str:
    prefix = f"{name}:"
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    raise RuntimeError("PROCESS_STATUS_FIELD_MISSING")


def _cgroup(name: str) -> str:
    return (Path("/sys/fs/cgroup") / name).read_text(encoding="utf-8").strip()


def _tmp_mount_options() -> list[str]:
    for line in Path("/proc/mounts").read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[1] == "/tmp":
            return sorted(fields[3].split(","))
    raise RuntimeError("TMP_MOUNT_MISSING")


def _egress_blocked() -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.settimeout(0.2)
        return probe.connect_ex(("1.1.1.1", 443)) != 0
    finally:
        probe.close()


def _root_read_only() -> bool:
    try:
        descriptor = os.open(
            "/aioa-root-write-proof",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
            0o600,
        )
    except OSError:
        return True
    os.close(descriptor)
    os.unlink("/aioa-root-write-proof")
    return False


def _privileged_operation_denied() -> bool:
    try:
        os.setuid(0)
    except PermissionError:
        return True
    return False


def main() -> int:
    soft_open_files, hard_open_files = resource.getrlimit(resource.RLIMIT_NOFILE)
    routes = Path("/proc/net/route").read_text(encoding="utf-8").splitlines()[1:]
    result = {
        "cap_eff": _status_value("CapEff"),
        "cpu_max": _cgroup("cpu.max"),
        "default_route_present": any(
            len(fields := line.split()) > 1 and fields[1] == "00000000" for line in routes
        ),
        "docker_socket_present": any(
            Path(path).exists() for path in ("/var/run/docker.sock", "/run/docker.sock")
        ),
        "egress_probe_blocked": _egress_blocked(),
        "gid": os.getgid(),
        "hard_open_files": hard_open_files,
        "host_aws_present": Path("/home/l/.aws").exists(),
        "host_home_present": Path("/home/l").exists(),
        "host_ssh_present": Path("/home/l/.ssh").exists(),
        "memory_max": _cgroup("memory.max"),
        "no_new_privs": _status_value("NoNewPrivs"),
        "pids_max": _cgroup("pids.max"),
        "privileged_operation_denied": _privileged_operation_denied(),
        "root_read_only": _root_read_only(),
        "sensitive_environment_names": sorted(
            name
            for name in os.environ
            if any(marker in name.upper() for marker in SENSITIVE_ENV_PARTS)
        ),
        "soft_open_files": soft_open_files,
        "tmp_mount_options": _tmp_mount_options(),
        "uid": os.getuid(),
    }
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

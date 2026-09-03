"""Packaged, server-owned copy of the certified synthetic W1 incident fixture."""

from __future__ import annotations

import base64
import os
import stat
from pathlib import Path
from typing import Final

from aioa_cloudops_agent.workspace import (
    W2_CERTIFIED_W1_ROOT_DIGEST,
    WORKSPACE_REMEDIATION_V1,
    FixtureIntegrityError,
    inspect_fixture_tree,
)

_FIXTURE_FILES: Final[dict[str, str]] = {
    "deployment.log": "MjAyNi0wOC0zMVQyMToxNDowMFogW2J1aWxkXSBpbWFnZSBidWlsZCBjb21wbGV0ZWQKMjAyNi0wOC0zMVQyMToxNDowM1ogW3J1bnRpbWVdIHN0YXJ0aW5nIGNvbmZpZ3VyZWQgRG9ja2VyIGNvbW1hbmQgKHNhbml0aXplZCkKMjAyNi0wOC0zMVQyMToxNDowM1ogW3J1bnRpbWVdIG9wZXJhdG9yIGJvb3RzdHJhcCB2YWx1ZSBwcmVzZW50OiB5ZXMgKHZhbHVlIHN1cHByZXNzZWQpCjIwMjYtMDgtMzFUMjE6MTQ6MDNaIFtydW50aW1lXSAvYmluL3NoOiAxOiAvYmluL3NoIC1ldSAtYyAndW1hc2sgMDc3OyB0ZXN0IC1uICIke0FJT0FfT1BFUkFUT1JfVE9LRU46LX0iOyBwcmludGYgLi4uOyBjaG1vZCAwNjAwIC4uLjsgdW5zZXQgQUlPQV9PUEVSQVRPUl9UT0tFTjsgZXhlYyBweXRob24gLW0gYWlvYV9jbG91ZG9wc19hZ2VudC5wb3J0YWJsZV9zZXJ2ZXInOiBGaWxlIG5hbWUgdG9vIGxvbmcKMjAyNi0wOC0zMVQyMToxNDowM1ogW3J1bnRpbWVdIHByb2Nlc3MgZXhpdGVkIHdpdGggc3RhdHVzIDEyNwoyMDI2LTA4LTMxVDIxOjE0OjA1WiBbcHJvYmVdIEdFVCAvcmVhZHkgY291bGQgbm90IGNvbm5lY3QgYmVjYXVzZSB0aGUgcHJvY2VzcyBoYWQgZXhpdGVkCg==",
    "expected_runtime_contract.json": "ewogICJmaXh0dXJlX3ZlcnNpb24iOiAid29ya3NwYWNlX3JlbmRlcl9pbmNpZGVudF92MSIsCiAgImlkZW50aWZpZXJzX2FyZV9zeW50aGV0aWMiOiB0cnVlLAogICJyZXF1aXJlZF9jaGlsZF9hcmd2IjogWwogICAgInB5dGhvbiIsCiAgICAiLW0iLAogICAgImFpb2FfY2xvdWRvcHNfYWdlbnQucG9ydGFibGVfc2VydmVyIgogIF0sCiAgInJlcXVpcmVkX2hlYWx0aF9wYXRocyI6IFsKICAgICIvaGVhbHRoIiwKICAgICIvcmVhZHkiCiAgXSwKICAic3RhcnR1cF9pbnZhcmlhbnRzIjogewogICAgImJvb3RzdHJhcF9zZWNyZXRfYWJzZW50X2Zyb21fY2hpbGRfZW52aXJvbm1lbnQiOiB0cnVlLAogICAgImZhaWxfY2xvc2VkX3doZW5fYm9vdHN0cmFwX3NlY3JldF9taXNzaW5nIjogdHJ1ZSwKICAgICJvcGVyYXRvcl90b2tlbl9maWxlX21vZGUiOiAiMDYwMCIsCiAgICAic3RhcnR1cF9lbnRyeV9pc19maXhlZF9hdWRpdGFibGVfZXhlY3V0YWJsZSI6IHRydWUKICB9LAogICJydW50aW1lX2ludmFyaWFudHMiOiB7CiAgICAiYXV0aG9yaXR5X21vZGUiOiAiSFVNQU5fQVBQUk9WQUxfUkVRVUlSRUQiLAogICAgImF3c19pbnRlZ3JhdGlvbl9lbmFibGVkIjogZmFsc2UsCiAgICAibW9kZWxfcHJvdmlkZXIiOiAibW9jayIsCiAgICAibmV0d29ya19lZ3Jlc3NfYWxsb3dlZCI6IGZhbHNlCiAgfQp9Cg==",
    "render.yaml": "c2VydmljZXM6CiAgLSB0eXBlOiB3ZWIKICAgIG5hbWU6IHN5bnRoZXRpYy1haW9hLXdvcmtzcGFjZS1pbmNpZGVudAogICAgcnVudGltZTogZG9ja2VyCiAgICBwbGFuOiBmcmVlCiAgICByZWdpb246IGZyYW5rZnVydAogICAgaGVhbHRoQ2hlY2tQYXRoOiAvcmVhZHkKICAgIGRvY2tlckNvbW1hbmQ6ID4tCiAgICAgIC9iaW4vc2ggLWV1IC1jICd1bWFzayAwNzc7IHRlc3QgLW4gIiR7QUlPQV9PUEVSQVRPUl9UT0tFTjotfSIgfHwgeyBwcmludGYgIiVzXG4iICJvcGVyYXRvciBib290c3RyYXAgbWlzc2luZyIgPiYyOyBleGl0IDI7IH07IHByaW50ZiAiJXNcbiIgIiRBSU9BX09QRVJBVE9SX1RPS0VOIiA+ICIkQUlPQV9MT0NBTF9BUElfVE9LRU5fUEFUSCI7IGNobW9kIDA2MDAgIiRBSU9BX0xPQ0FMX0FQSV9UT0tFTl9QQVRIIjsgdW5zZXQgQUlPQV9PUEVSQVRPUl9UT0tFTjsgZXhlYyBweXRob24gLW0gYWlvYV9jbG91ZG9wc19hZ2VudC5wb3J0YWJsZV9zZXJ2ZXInCiAgICBlbnZWYXJzOgogICAgICAtIGtleTogQUlPQV9SVU5USU1FX01PREUKICAgICAgICB2YWx1ZTogcG9ydGFibGUKICAgICAgLSBrZXk6IEFJT0FfTU9ERUxfUFJPVklERVIKICAgICAgICB2YWx1ZTogbW9jawogICAgICAtIGtleTogQUlPQV9BV1NfSU5URUdSQVRJT05fRU5BQkxFRAogICAgICAgIHZhbHVlOiAiZmFsc2UiCiAgICAgIC0ga2V5OiBBSU9BX1BPUlQKICAgICAgICB2YWx1ZTogIjEwMDAwIgogICAgICAtIGtleTogQUlPQV9MT0NBTF9BUElfVE9LRU5fUEFUSAogICAgICAgIHZhbHVlOiAvdmFyL2xpYi9haW9hL29wZXJhdG9yLnRva2VuCiAgICAgIC0ga2V5OiBBSU9BX09QRVJBVE9SX1RPS0VOCiAgICAgICAgc3luYzogZmFsc2UK",
    "README.md": "IyBTeW50aGV0aWMgUmVuZGVyIHJ1bnRpbWUtc3RhcnQgaW5jaWRlbnQKClRoaXMgZGV0ZXJtaW5pc3RpYyBmaXh0dXJlIGlzIGEgc2FuaXRpemVkIHJlY29uc3RydWN0aW9uIGZvciByZWFkLW9ubHkgaW52ZXN0aWdhdGlvbi4gQWxsIGRhdGVzLApzZXJ2aWNlIG5hbWVzIGFuZCBpZGVudGlmaWVycyBhcmUgc3ludGhldGljLiBUb2tlbiB2YWx1ZXMsIGNvb2tpZXMsIG5vbmNlcywgYWNjb3VudCBpZGVudGlmaWVycywKcHJvdmlkZXIgbWV0YWRhdGEsIHBlcnNvbmFsIGRhdGEsIGhvc3QgcGF0aHMgYW5kIEFXUyBjcmVkZW50aWFscyBhcmUgaW50ZW50aW9uYWxseSBhYnNlbnQuCgpUaGUgZXZpZGVuY2Ugc2V0IGNvbnRhaW5zIHRoZSBvYnNlcnZlZCBkZXBsb3ltZW50IG91dHB1dCwgdGhlIGNvbmZpZ3VyYXRpb24gcHJlc2VudGVkIHRvIHRoZQpydW50aW1lLCBhIGNhbmRpZGF0ZSBmaXhlZCBzdGFydHVwIGV4ZWN1dGFibGUsIGFuZCB0aGUgZXhwZWN0ZWQgcnVudGltZSBpbnZhcmlhbnRzLiBJbnZlc3RpZ2F0b3JzCnNob3VsZCBkaXN0aW5ndWlzaCBvYnNlcnZlZCBmYWN0cyBmcm9tIGh5cG90aGVzZXMsIGNvbXBhcmUgbW9yZSB0aGFuIG9uZSBwbGF1c2libGUgZmFpbHVyZSBjYXVzZSwKYW5kIGNpdGUgYXJ0aWZhY3QgcGF0aHMgYW5kIFNIQS0yNTYgaWRlbnRpdGllcy4KClRoZSBmaXh0dXJlIGdyYW50cyBubyBhdXRob3JpdHkgdG8gZWRpdCBmaWxlcywgZXhlY3V0ZSBjb21tYW5kcywgYWNjZXNzIGEgbmV0d29yaywgaW5zdGFsbApkZXBlbmRlbmNpZXMsIG9wZXJhdGUgR2l0IG9yIGFwcGx5IGEgcmVwYWlyLiBBbiBleGFjdCBwYXRjaCBwcm9wb3NhbCBiZWxvbmdzIHRvIFBoYXNlIFcyLgo=",
    "scripts/render_start.sh": "IyEvYmluL3NoCnNldCAtZXUKCnVtYXNrIDA3NwoKaWYgWyAteiAiJHtBSU9BX09QRVJBVE9SX1RPS0VOOi19IiBdOyB0aGVuCiAgICBwcmludGYgJyVzXG4nICdBSU9BIG9wZXJhdG9yIHRva2VuIG1pc3NpbmcnID4mMgogICAgZXhpdCAyCmZpCgppZiBbIC16ICIke0FJT0FfTE9DQUxfQVBJX1RPS0VOX1BBVEg6LX0iIF07IHRoZW4KICAgIHByaW50ZiAnJXNcbicgJ0FJT0EgbG9jYWwgQVBJIHRva2VuIHBhdGggbWlzc2luZycgPiYyCiAgICBleGl0IDIKZmkKCnByaW50ZiAnJXNcbicgIiRBSU9BX09QRVJBVE9SX1RPS0VOIiA+ICIkQUlPQV9MT0NBTF9BUElfVE9LRU5fUEFUSCIKY2htb2QgMDYwMCAiJEFJT0FfTE9DQUxfQVBJX1RPS0VOX1BBVEgiCnVuc2V0IEFJT0FfT1BFUkFUT1JfVE9LRU4KCmV4ZWMgcHl0aG9uIC1tIGFpb2FfY2xvdWRvcHNfYWdlbnQucG9ydGFibGVfc2VydmVyCg==",
}


def ensure_workspace_hero_fixture(root: Path) -> Path:
    """Create or verify the exact packaged fixture without accepting caller content."""

    if not isinstance(root, Path) or not str(root).strip() or ".." in root.parts:
        raise FixtureIntegrityError("workspace hero fixture root is invalid")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    metadata = root.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise FixtureIntegrityError("workspace hero fixture root must be a real directory")
    for relative_path, encoded in _FIXTURE_FILES.items():
        destination = root.joinpath(*relative_path.split("/"))
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        destination.parent.chmod(0o700)
        expected = base64.b64decode(encoded, validate=True)
        if destination.exists():
            if destination.is_symlink() or destination.read_bytes() != expected:
                raise FixtureIntegrityError("packaged workspace hero fixture drifted")
            destination.chmod(0o400)
            continue
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(destination, flags, 0o600)
        try:
            offset = 0
            while offset < len(expected):
                written = os.write(descriptor, expected[offset:])
                if written <= 0:
                    raise OSError("workspace hero fixture write made no progress")
                offset += written
            os.fchmod(descriptor, 0o400)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    _artifacts, digest = inspect_fixture_tree(root, WORKSPACE_REMEDIATION_V1)
    if digest != W2_CERTIFIED_W1_ROOT_DIGEST:
        raise FixtureIntegrityError("packaged workspace hero fixture digest is uncertified")
    return root

#!/usr/bin/env python3
"""Create a candidate-bound, authenticated Day 15 operator preflight attestation."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import stat
import sys
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.day15.preflight_region import validate_judge_token_not_after  # noqa: E402
from scripts.day15.validate_template import (  # noqa: E402
    DEFAULT_TEMPLATE,
    TemplateFailure,
    canonical_json,
    compare_lambda_configuration_sha256,
    has_sam_transform,
    load_template,
)

DEFAULT_ARTIFACT: Final = ROOT / "dist" / "day15" / "aioa-lambda.zip"
DEFAULT_MANIFEST: Final = ROOT / "dist" / "day15" / "aioa-lambda.manifest.json"
DEFAULT_RENDERED_TEMPLATE: Final = ROOT / "dist" / "day15" / "rendered-template.yaml"
DEFAULT_RECEIPT: Final = ROOT / "dist" / "day15" / "external-preflight.json"
GENERATOR_PATH: Final = Path(__file__).absolute()
SHA256_LENGTH: Final = 64
ATTESTATION: Final = "AUTHORIZED_OPERATOR_CONFIRMS_READ_ONLY_EXTERNAL_PREFLIGHT"
PROVENANCE: Final = "OPERATOR_HELD_HMAC_SHA256"
COST_NOTIFICATION_CURRENCY: Final = "USD"
COST_NOTIFICATION_THRESHOLDS: Final = (10, 25, 40)
CHECK_NAMES: Final = (
    "artifact_bucket_ready",
    "authorized_profile_ready",
    "bedrock_access_ready",
    "cost_notification_owned",
    "judge_secret_plan_ready",
    "sandbox_target_ready",
)
BINDING_NAMES: Final = frozenset(
    {
        "artifact_manifest_sha256",
        "artifact_sha256",
        "configuration_sha256",
        "generator_sha256",
        "judge_token_not_after_sha256",
        "rendered_template_sha256",
        "repository_commit_oid",
        "template_sha256",
    }
)


class AttestationFailure(RuntimeError):
    def __init__(self, reason: str, *, status: str = "FAIL") -> None:
        self.reason = reason
        self.status = status
        super().__init__(reason)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_regular_file(path: Path, reason: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise AttestationFailure(reason, status="BLOCKED")
    try:
        return path.read_bytes()
    except OSError as error:
        raise AttestationFailure(reason, status="BLOCKED") from error


def _canonical_object(path: Path, reason: str) -> tuple[dict[str, object], bytes]:
    raw = _read_regular_file(path, reason)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AttestationFailure(reason) from error
    if not isinstance(value, dict) or raw != (canonical_json(value) + "\n").encode():
        raise AttestationFailure(reason)
    return value, raw


def read_attestation_key(path: Path | None) -> bytes:
    """Load an operator-held key that cannot be committed or world-readable."""

    if path is None or path.is_symlink() or not path.is_file():
        raise AttestationFailure("EXTERNAL_ATTESTATION_KEY_REQUIRED", status="BLOCKED")
    resolved = path.resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise AttestationFailure("EXTERNAL_ATTESTATION_KEY_INSIDE_REPOSITORY")
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
        key = path.read_bytes()
    except OSError as error:
        raise AttestationFailure(
            "EXTERNAL_ATTESTATION_KEY_UNAVAILABLE", status="BLOCKED"
        ) from error
    if mode & 0o077:
        raise AttestationFailure("EXTERNAL_ATTESTATION_KEY_PERMISSIONS_UNSAFE")
    if not 32 <= len(key) <= 4_096:
        raise AttestationFailure("EXTERNAL_ATTESTATION_KEY_INVALID")
    return key


def candidate_bindings(
    *,
    artifact: Path,
    manifest: Path,
    template: Path,
    rendered_template: Path,
    configuration_sha256: str,
    judge_token_not_after: str,
) -> dict[str, str]:
    """Bind an attestation to code, config, rendering, source commit, and expiry."""

    artifact_raw = _read_regular_file(artifact, "ATTESTATION_ARTIFACT_REQUIRED")
    manifest_model, manifest_raw = _canonical_object(
        manifest,
        "ATTESTATION_MANIFEST_REQUIRED",
    )
    try:
        template_model = load_template(template)
        rendered_model = load_template(rendered_template)
        digest_status, _, computed_digest = compare_lambda_configuration_sha256(
            template_model,
            configuration_sha256,
        )
    except TemplateFailure as error:
        raise AttestationFailure("ATTESTATION_TEMPLATE_INVALID") from error
    if digest_status != "PASS" or computed_digest != configuration_sha256:
        raise AttestationFailure("ATTESTATION_CONFIGURATION_DIGEST_MISMATCH")
    if has_sam_transform(rendered_model):
        raise AttestationFailure("ATTESTATION_RENDERED_TEMPLATE_REQUIRED", status="BLOCKED")
    artifact_sha256 = _sha256(artifact_raw)
    artifact_model = manifest_model.get("artifact")
    repository = manifest_model.get("repository")
    if (
        not isinstance(artifact_model, Mapping)
        or artifact_model.get("sha256") != artifact_sha256
        or not isinstance(repository, Mapping)
    ):
        raise AttestationFailure("ATTESTATION_MANIFEST_BINDING_INVALID")
    commit_oid = repository.get("commit_oid")
    if (
        not isinstance(commit_oid, str)
        or len(commit_oid) not in {40, 64}
        or any(character not in "0123456789abcdef" for character in commit_oid)
    ):
        raise AttestationFailure("ATTESTATION_COMMIT_BINDING_INVALID")
    generator_raw = _read_regular_file(GENERATOR_PATH, "ATTESTATION_GENERATOR_UNAVAILABLE")
    return {
        "artifact_manifest_sha256": _sha256(manifest_raw),
        "artifact_sha256": artifact_sha256,
        "configuration_sha256": configuration_sha256,
        "generator_sha256": _sha256(generator_raw),
        "judge_token_not_after_sha256": _sha256(judge_token_not_after.encode()),
        "rendered_template_sha256": _sha256(canonical_json(rendered_model).encode()),
        "repository_commit_oid": commit_oid,
        "template_sha256": _sha256(canonical_json(template_model).encode()),
    }


def _unsigned_receipt(bindings: Mapping[str, str]) -> dict[str, object]:
    if set(bindings) != BINDING_NAMES or any(
        not isinstance(value, str) or len(value) not in {40, SHA256_LENGTH}
        for value in bindings.values()
    ):
        raise AttestationFailure("EXTERNAL_ATTESTATION_BINDINGS_INVALID")
    return {
        "attestation": ATTESTATION,
        "bindings": dict(bindings),
        "checks": {name: "PASS" for name in CHECK_NAMES},
        "cost_notifications": {
            "currency": COST_NOTIFICATION_CURRENCY,
            "thresholds": list(COST_NOTIFICATION_THRESHOLDS),
        },
        "provenance": PROVENANCE,
        "sanitized": True,
        "schema_version": 3,
    }


def create_receipt(bindings: Mapping[str, str], key: bytes) -> dict[str, object]:
    unsigned = _unsigned_receipt(bindings)
    mac = hmac.new(key, canonical_json(unsigned).encode(), hashlib.sha256).hexdigest()
    return {**unsigned, "attestation_hmac_sha256": mac}


def validate_receipt(
    receipt: object,
    *,
    expected_bindings: Mapping[str, str],
    key: bytes,
) -> None:
    if not isinstance(receipt, dict):
        raise AttestationFailure("EXTERNAL_ATTESTATION_SCHEMA_INVALID")
    mac = receipt.get("attestation_hmac_sha256")
    unsigned = {name: value for name, value in receipt.items() if name != "attestation_hmac_sha256"}
    if unsigned != _unsigned_receipt(expected_bindings) or not isinstance(mac, str):
        raise AttestationFailure("EXTERNAL_ATTESTATION_SCHEMA_OR_BINDING_INVALID")
    expected_mac = hmac.new(key, canonical_json(unsigned).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, expected_mac):
        raise AttestationFailure("EXTERNAL_ATTESTATION_AUTHENTICATION_FAILED")


def _atomic_write(path: Path, payload: dict[str, object]) -> None:
    if path.is_symlink():
        raise AttestationFailure("EXTERNAL_ATTESTATION_OUTPUT_SYMLINK_FORBIDDEN")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix="day15-attestation-",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write((canonical_json(payload) + "\n").encode())
    try:
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _exit_code(status: str) -> int:
    return {"PASS": 0, "FAIL": 1, "PARTIAL": 2, "BLOCKED": 3}.get(status, 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--rendered-template", type=Path, default=DEFAULT_RENDERED_TEMPLATE)
    parser.add_argument("--configuration-sha256", required=True)
    parser.add_argument("--judge-token-not-after", required=True)
    parser.add_argument("--attestation-key-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_RECEIPT)
    for check_name in CHECK_NAMES:
        parser.add_argument(f"--confirm-{check_name.replace('_', '-')}", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        missing = [name for name in CHECK_NAMES if not getattr(args, f"confirm_{name}")]
        if missing:
            raise AttestationFailure("EXTERNAL_PREFLIGHT_CONFIRMATIONS_REQUIRED", status="BLOCKED")
        expiry = validate_judge_token_not_after(
            args.judge_token_not_after,
            clock=lambda: datetime.now(UTC),
        )
        if expiry.status != "PASS":
            raise AttestationFailure(expiry.reasons[0], status=expiry.status)
        key = read_attestation_key(args.attestation_key_file)
        bindings = candidate_bindings(
            artifact=args.artifact,
            manifest=args.manifest,
            template=args.template,
            rendered_template=args.rendered_template,
            configuration_sha256=args.configuration_sha256,
            judge_token_not_after=args.judge_token_not_after,
        )
        receipt = create_receipt(bindings, key)
        _atomic_write(args.output, receipt)
        payload: dict[str, object] = {
            "receipt_sha256": _sha256((canonical_json(receipt) + "\n").encode()),
            "status": "PASS",
        }
    except AttestationFailure as error:
        payload = {"reasons": [error.reason], "status": error.status}
    if args.json:
        print(canonical_json(payload))
    else:
        reasons = ",".join(payload.get("reasons", [])) or "-"
        print(f"DAY15_EXTERNAL_ATTESTATION {payload['status']} reasons={reasons}")
    return _exit_code(str(payload["status"]))


if __name__ == "__main__":
    raise SystemExit(main())

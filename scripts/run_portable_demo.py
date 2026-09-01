"""Run the canonical AWS-free Strands judge sandbox and persist its evidence."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from aioa_cloudops_agent.config import RuntimeSettings
from aioa_cloudops_agent.domain import ContractValidationError
from aioa_cloudops_agent.portable import (
    PortableDemoError,
    render_portable_receipt,
    run_portable_demo,
    write_portable_receipt,
)
from aioa_cloudops_agent.release.post_deploy_verifier import PostDeployVerifierError

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / ".local" / "portable" / "portable-demo-receipt.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Preserve sandbox durable state in a new or empty directory.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        settings = RuntimeSettings.from_environment()
        if args.workspace is None:
            with tempfile.TemporaryDirectory(prefix="aioa-portable-demo-") as temporary:
                receipt = run_portable_demo(
                    settings=settings,
                    workspace=Path(temporary),
                )
        else:
            receipt = run_portable_demo(settings=settings, workspace=args.workspace)
        write_portable_receipt(args.output, receipt)
        rendered = render_portable_receipt(receipt)
        code = 0
    except ContractValidationError:
        rendered = (
            json.dumps(
                {
                    "aws_mutations": 0,
                    "external_network_connections": 0,
                    "reason": "PORTABLE_RUNTIME_CONFIGURATION_INVALID",
                    "status": "FAIL",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        code = 1
    except (PortableDemoError, PostDeployVerifierError) as error:
        rendered = (
            json.dumps(
                {
                    "aws_mutations": 0,
                    "external_network_connections": 0,
                    "reason": error.reason,
                    "status": "FAIL",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        code = 1
    print(rendered, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

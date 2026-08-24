# AIOA Non-Zero CloudOps — Bounded Idle EC2 Remediation Agent

Newly authored work for the **AWS Agents for Humans Hackathon 2026**.

- Track: Professional Agents
- Status: Day 14 P1, AU-3 reviewer evidence, and fresh-environment reproducibility are complete locally; Day 15 deployment and live AWS mutation have not run
- Orchestration: one Strands Agent
- Model platform: Amazon Bedrock
- Current capability: five bounded tools covering investigation, proposal-bound stop, and independent verification
- Safety boundary: executable P0/P1 matrices, bounded dependency circuits, deterministic reviewer evidence, and an independent fail-closed emergency veto immediately around the private mutation boundary

## Non-Zero Principle

No silent, ambiguous, untraceable, unverifiable, or falsely-successful state may pass as a valid result.

This repository contains newly authored hackathon work. Existing AIOA, AOIA, and Non-Zero projects are prior art; no implementation code from them has been imported.

No AWS infrastructure has been deployed by this project. A private, tightly scoped stop executor is implemented but defaults disabled and has not been invoked against live EC2. Final Devpost submission text is **NOT yet canonical**.

## Local quickstart

Prerequisites are Git, Python 3.12+ with virtual-environment support, and network access only for cloning and installing declared dependencies. No AWS credentials are required; AWS writes remain disabled.

```bash
git clone https://github.com/luciferprosun/AIOA-NonZero-CloudOps-Agent.git
cd AIOA-NonZero-CloudOps-Agent
python3.12 -m venv .venv
.venv/bin/python -m pip install ".[dev]"
.venv/bin/python -m pytest -q
.venv/bin/python scripts/run_p0_gate.py
.venv/bin/python scripts/run_p1_gate.py
.venv/bin/python scripts/build_reviewer_evidence_manifest.py --check
.venv/bin/python scripts/validate_reviewer_evidence_manifest.py
```

The P1 runner includes the clean-clone proof. To run only that reproducibility check:

```bash
.venv/bin/python scripts/prove_clean_clone.py --mode auto
```

The harness creates another disposable environment with `python -m venv`. On hosts where the standard-library module lacks `ensurepip`, the declared dev dependency provides the documented `python -m virtualenv` fallback. These checks use mocks and static proof. They do not deploy infrastructure or call live AWS services.

The deterministic claim-to-proof index is in [`docs/evidence/`](docs/evidence/). Day 15 prerequisites and known deployment gaps are frozen in [`docs/architecture/day-15-deployment-readiness.md`](docs/architecture/day-15-deployment-readiness.md); AU-2 remains evaluation-only in [`docs/architecture/au-2-risk-evaluation.md`](docs/architecture/au-2-risk-evaluation.md).

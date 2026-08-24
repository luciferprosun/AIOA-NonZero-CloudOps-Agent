# AIOA Non-Zero CloudOps — Bounded Idle EC2 Remediation Agent

Newly authored work for the **AWS Agents for Humans Hackathon 2026**.

- Track: Professional Agents
- Status: complete local human-approved remediation, restart-safe recovery, and Day 12 safety hardening; live AWS mutation not run without explicit gates
- Orchestration: one Strands Agent
- Model platform: Amazon Bedrock
- Current capability: five bounded tools covering investigation, proposal-bound stop, and independent verification
- Safety boundary: exact default-deny dispatch, durable/audited budgets, bounded schema correction and read retry

## Non-Zero Principle

No silent, ambiguous, untraceable, unverifiable, or falsely-successful state may pass as a valid result.

This repository contains newly authored hackathon work. Existing AIOA, AOIA, and Non-Zero projects are prior art; no implementation code from them has been imported.

No AWS infrastructure has been deployed by this project. A private, tightly scoped stop executor is implemented but defaults disabled and has not been invoked against live EC2. Final Devpost submission text is **NOT yet canonical**.

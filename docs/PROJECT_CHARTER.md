# Project Charter

## Frozen Product-Level Decisions

| Key | Value |
| --- | --- |
| PROJECT | AIOA Non-Zero CloudOps Agent |
| HACKATHON | AWS Agents for Humans |
| TRACK | Professional Agents |
| LANGUAGE | Python |
| AGENT_ARCHITECTURE | Single Strands Agent |
| MODEL_PLATFORM | Amazon Bedrock |
| NZ_CONTROL_PLANE | Custom deterministic application layer |
| DURABLE_SOURCE_OF_TRUTH | DynamoDB |
| EVIDENCE_ARTIFACTS | S3 |
| TELEMETRY | CloudWatch / OpenTelemetry |
| AUTHORITY_MODEL | AUTO / PLAN_AND_CONFIRM / NEVER_AUTONOMOUS |
| AGENTCORE | NOT_ON_P0_CRITICAL_PATH |
| NO_LEGACY_CODE_IMPORT | TRUE |
| EXACT_CLOUDOPS_USE_CASE | NOT_YET_FROZEN |

## Current Boundary

The project has pre-deployment Non-Zero persistence contracts and one narrow read-only observation capability for unattached Elastic IP discovery. No Strands agent, Bedrock integration, remediation, telemetry pipeline, live data-store operation, or deployment has been implemented.

This first observation capability does not freeze the complete product scope. The exact CloudOps use case remains intentionally unfrozen and must be selected through an authorized product-scope decision.

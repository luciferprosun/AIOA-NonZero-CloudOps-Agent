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
| EXACT_CLOUDOPS_USE_CASE | BOUNDED_IDLE_EC2_REMEDIATION_AGENT |

## Current Boundary

The project is a bounded idle-EC2 remediation agent for exactly one allow-listed sandbox instance. The canonical maximum tool surface is `inspect_instance`, `read_utilization_metrics`, `build_remediation_evidence`, `stop_sandbox_instance`, and `verify_instance_state`.

The current implementation contains only `inspect_instance`, classified `READ_ONLY` under `AUTO`. Strands orchestrates, the model proposes, and the deterministic Non-Zero layer controls valid state and authority. No remediation tool, AWS deployment, live state write, or EC2 mutation has been implemented.

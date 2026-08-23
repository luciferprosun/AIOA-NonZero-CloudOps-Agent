# Phase 2 Strands and Bedrock Compatibility Spike

## Runtime Boundary

This repository pins `strands-agents[otel]==1.53.0` and creates exactly one primary Strands `Agent`. The explicit Amazon Bedrock development candidate is `eu.amazon.nova-2-lite-v1:0` in source region `eu-central-1`, with temperature `0` and a maximum output of `1024` tokens. There is no fallback model.

The `eu.` model identifier is an AWS European geographic inference profile. Requests originate in `eu-central-1`; AWS may route inference within the profile's supported European Regions, which remains a data-residency consideration for deployment review.

## Canonical Tool Surface

The only registered tool in this step is `inspect_instance`. It calls only `ec2:DescribeInstances`, always supplies the one configured instance ID, and accepts the result only when the returned ID and required sandbox tag both match. Its normalized result excludes raw provider structures and carries deterministic evidence under the execution UUIDv7 correlation ID.

The Phase 1 unattached-Elastic-IP QueryResource experiment remains preserved by `phase1-foundation-green`, but no EIP tool or `ec2:DescribeAddresses` authority remains active on `main`. The final canonical tool cap is five; tools two through five are not implemented in this step.

## Authority and Intervention

Native Strands `HumanInTheLoop` allows only `inspect_instance` without confirmation. Any unlisted future tool interrupts for approval rather than inheriting `AUTO`. Session trust and wildcard tool allowance are disabled. Configuration is not human approval, model text is not authority, and no mutation implementation exists.

Strands orchestrates. The model proposes. Non-Zero determines valid state and authority.

## Correlation and Telemetry

OpenTelemetry-compatible attributes associate the UUIDv7 correlation ID with the Strands invocation, model loop, tool call, typed result, and append-oriented provenance event. No remote collector is configured, and raw credential-bearing AWS responses are not recorded.

## Current Limits

No infrastructure was deployed. No live EC2 call, DynamoDB write, IAM change, resource mutation, remediation tool, AgentCore component, shell tool, arbitrary URL tool, or multi-agent architecture was added. The bounded live compatibility result, when attempted, is reported separately from deterministic implementation validity.

## Bounded Live Compatibility Result

AWS identity, the EU inference profile, and the Nova 2 Lite foundation-model metadata were available in `eu-central-1`. The one authorized Strands workflow reached Bedrock once, but Bedrock rejected the initial model request with `ValidationException` before any tool call. No retry and no fallback model were used. Counts were one workflow, one Bedrock model call, zero tool executions, zero live EC2 calls, and zero DynamoDB writes.

`MODEL_STATUS = COMPATIBILITY_FAILED`.

The current [Nova 2 request schema](https://docs.aws.amazon.com/nova/latest/nova2-userguide/request-response-schema.html) lists a positive minimum for `temperature`, while the frozen project contract requires deterministic `temperature = 0`. This is a likely cause, not a proven error-message attribution, because credential-bearing provider details were deliberately not recorded. The conflict must be resolved explicitly before Phase 2 Step 2; this step does not weaken the guardrail or switch models.

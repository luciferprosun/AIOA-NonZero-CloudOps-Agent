# AWS Boundary and Cost Guardrails

## Execution Boundary

The application boundary is fixed to `eu-central-1`. Future runtime work may use Lambda and API Gateway, Strands Agents SDK, Amazon Bedrock with Claude 3 Haiku, DynamoDB, and an S3/CloudFront UI. AgentCore is not used.

AWS operations are classified through a closed catalog:

- read-only discovery may use `AUTO`;
- mutations must never use `AUTO`;
- `PLAN_AND_CONFIRM` may produce a proposal, but execution requires both the global mutation capability and separate explicit human approval;
- `NEVER_AUTONOMOUS` operations cannot be executed autonomously, even when configuration and approval are present.

AWS mutations are globally disabled by default. Configuration enabling AWS writes is not authorization to perform a specific mutation. Missing or malformed configuration fails explicitly.

## IAM Boundary

`CloudOpsReadOnlyRole` and `CloudOpsRemediationRole` are separate future roles. The read-only template grants only EC2 address, instance, Security Group, and tag discovery. Those EC2 `Describe` actions do not support resource-level scoping, so the documented `Resource: "*"` limitation is constrained by exact actions and the `eu-central-1` condition.

The remediation template grants only a future, approved release of one tagged Elastic IP through a generic resource ARN. No Security Group mutation is granted. Templates contain no account ID, principal, credential, trust policy, or secret, and nothing was deployed.

## Cost Boundary

- budget warning: USD 10;
- elevated warning: USD 25;
- critical warning: USD 40;
- model output cap: 1024 tokens;
- DynamoDB billing: `PAY_PER_REQUEST`;
- CloudWatch retention: 3 days.

Threshold ordering and service limits are typed and validated. No AWS Budget, AWS resource, model invocation, or deployment occurred in this step.

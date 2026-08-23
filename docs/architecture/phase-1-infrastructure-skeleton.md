# Phase 1 Infrastructure Skeleton

## Implemented as Infrastructure Code

- AWS SAM / CloudFormation template;
- Amazon API Gateway HTTP API exposing only `GET /health`;
- deterministic Python 3.12 health Lambda with 256 MB memory, 10-second timeout, and reserved concurrency of 2;
- explicit Lambda execution role limited to log-stream creation and log-event delivery;
- explicit Lambda log group with 3-day retention;
- encrypted DynamoDB state-table skeleton using `PAY_PER_REQUEST` with string `PK` and `SK` keys;
- non-sensitive outputs for the health endpoint, function name, and table name.

The table is only a future state/provenance container. Execution, correlation, idempotency, provenance, and approval record schemas remain deferred to Phase 1 / Step 4.

## Not Implemented

Strands, Bedrock, CloudOps `QueryResource`, DynamoDB Non-Zero persistence, human-in-the-loop approval, approval tokens, remediation execution, S3/CloudFront UI, AgentCore, and deployment are not implemented.

## Security Boundary

The health Lambda receives safe configuration, including `AWS_MUTATIONS_ENABLED=false`, but has no DynamoDB, EC2, Bedrock, S3, IAM, or remediation permission. The current Lambda has no AWS CloudOps authority and cannot perform remediation. Step 2 read-only and remediation role designs remain separate and are not attached.

Infrastructure code exists, but nothing was deployed to AWS during this step. AWS resource creates, updates, deletes, and Bedrock invocations remained zero.

Reference: <https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-specification.html>

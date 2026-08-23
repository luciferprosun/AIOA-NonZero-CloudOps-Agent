# IAM Design Boundary

These policy documents are public-safe design templates only. They were not deployed and contain no account identifiers, principals, trust policies, or credentials.

## CloudOpsReadOnlyRole

`cloudops-read-only-policy.json` permits only `ec2:DescribeInstances` for the canonical `inspect_instance` tool. The AWS EC2 Service Authorization Reference does not support resource-level scoping for this action, so the policy requires `Resource: "*"`. The application therefore independently requires one configured instance ID and a matching sandbox tag before accepting the result. The statement limits requests to `eu-central-1` and grants no mutation action.

## CloudOpsRemediationRole

No remediation policy is active in this step. A future `stop_sandbox_instance` design requires a separate least-privilege review, deterministic authority tests, human approval, and explicit authorization before any IAM policy is added or deployed.

Configuration does not authorize a mutation. The global mutation flag, explicit human approval, application boundary, and remediation role are independent controls.

Reference: <https://docs.aws.amazon.com/service-authorization/latest/reference/list_ec2.html>

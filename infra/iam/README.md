# IAM Design Boundary

These policy documents are public-safe design templates only. They were not deployed and contain no account identifiers, principals, trust policies, or credentials.

## CloudOpsReadOnlyRole

`cloudops-read-only-policy.json` permits only `ec2:DescribeInstances` and `cloudwatch:GetMetricStatistics` for the canonical `inspect_instance` and `read_utilization_metrics` tools. These read APIs do not support useful resource-level scoping, so the policy requires `Resource: "*"`. The application independently requires one configured instance ID, matching sandbox tag proof, fixed namespace/metric/dimension, and `eu-central-1`. The policy grants no write or mutation action.

## CloudOpsRemediationRole

No remediation policy is active in this step. A future `stop_sandbox_instance` design requires a separate least-privilege review, deterministic authority tests, human approval, and explicit authorization before any IAM policy is added or deployed.

Configuration does not authorize a mutation. The global mutation flag, explicit human approval, application boundary, and remediation role are independent controls.

Reference: <https://docs.aws.amazon.com/service-authorization/latest/reference/list_ec2.html>

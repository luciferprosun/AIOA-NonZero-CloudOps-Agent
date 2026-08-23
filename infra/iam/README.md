# IAM Design Boundary

These policy documents are public-safe design templates only. They were not deployed and contain no account identifiers, principals, trust policies, or credentials.

## CloudOpsReadOnlyRole

`cloudops-read-only-policy.json` permits only the four EC2 discovery calls required by the initial scope. The AWS EC2 Service Authorization Reference lists no resource type for these `Describe` actions, so their policy statement requires `Resource: "*"`. The statement still limits requests to `eu-central-1` and grants no mutation action.

## CloudOpsRemediationRole

`cloudops-remediation-policy.json` permits only `ec2:ReleaseAddress`. The generic Elastic IP ARN template must be rendered later with the deployment partition, account, and one approved allocation ID. It also requires the target tag `AIOACloudOpsManaged=true` and the `eu-central-1` request region.

The current remediation template intentionally grants no Security Group mutation. Any such permission requires a later explicit use-case decision, resource-scope review, authority review, and separate test coverage.

Configuration does not authorize a mutation. The global mutation flag, explicit human approval, application boundary, and remediation role are independent controls.

Reference: <https://docs.aws.amazon.com/service-authorization/latest/reference/list_ec2.html>

# QueryResource: Unattached Elastic IP Observation

The first CloudOps capability observes allocated Elastic IP addresses through only `ec2:DescribeAddresses`. It is classified `READ_ONLY` under the `AUTO` authority gate and has no remediation method.

An address is reported as unattached only when the response contains a valid address identity and no association, instance, network-interface, or private-IP relationship field. Missing, empty, malformed, or otherwise uncertain association evidence is recorded as ambiguous instead of being promoted to a finding.

Results are typed rather than exposing raw provider responses. Each finding contains only allowlisted non-secret evidence and a SHA-256 digest over canonical JSON. A completed query can be materialized as an append-only `CLOUDOPS_QUERY_COMPLETED` provenance event under the original UUIDv7 correlation ID.

The operation allowlist contains only `ec2:DescribeAddresses`. Mutation requests fail before the provider client is called. Finding a potentially unattached Elastic IP is not authorization to release it.

No AWS resource mutation, live AWS query, live DynamoDB write, Bedrock invocation, Strands execution, or deployment occurred in this implementation step.

# Day 15 deployment gate and alias rollback

The Day 15 tools prepare and verify a candidate; they do not authorize deployment. No deployment,
Function URL publication, live Bedrock call, or EC2 mutation was performed while creating this
runbook.

## Local validation sequence

1. Validate the fixed ten-gate schema without reading deployment inputs:

   ```bash
   .venv/bin/python scripts/day15/run_day15_gate.py --validate-only --json
   ```

2. Validate the SAM template locally:

   ```bash
   .venv/bin/python scripts/day15/validate_template.py --json
   ```

   The command requires SAM CLI `1.165.0`, cfn-lint `1.52.1`, and AWS SAM Translator `1.111.0`,
   exactly as recorded in `requirements/day15-toolchain.json`. Then create and independently
   verify the deterministic CloudFormation rendering:

   ```bash
   .venv/bin/python scripts/day15/render_template.py --json
   .venv/bin/python scripts/day15/render_template.py --verify --json
   ```

   The renderer replaces only the two reviewed local `CodeUri` values with the frozen
   `Day15ArtifactBucketName` and `Day15ArtifactObjectKey` parameters before invoking the pinned
   translator. Its provenance binds the source template, toolchain, renderer, validator helper,
   clean commit, packaging transform, and exact rendered bytes. Structural validation alone is
   useful, but a missing or mismatched pinned tool remains `PARTIAL`, `BLOCKED`, or `FAIL`.

3. Run the explicit region, token-expiry, and configuration preflight. The expiry must be a UTC
   ISO-8601 value strictly in the future and no more than 86,400 seconds from the preflight clock.
   The command never reads `AWS_REGION`, `AWS_DEFAULT_REGION`, or a token value and never echoes the
   expiry. First run without the configuration digest to obtain the deterministic computed digest;
   that run is intentionally `BLOCKED`:

   ```bash
   .venv/bin/python scripts/day15/preflight_region.py \
     --template infra/sam/template.yaml \
     --region eu-central-1 \
     --judge-token-not-after '<reviewed-UTC-expiry>' \
     --json
   ```

   Review the computed digest, then rerun with it:

   ```bash
   .venv/bin/python scripts/day15/preflight_region.py \
     --template infra/sam/template.yaml \
     --region eu-central-1 \
     --judge-token-not-after '<reviewed-UTC-expiry>' \
     --lambda-configuration-sha256 '<reviewed-configuration-sha256>' \
     --json
   ```

   Pass that same digest as the template parameter `LambdaConfigurationSha256`. It covers both
   functions' reviewed runtime/configuration/environment and their complete referenced execution
   roles. A configuration-only template edit changes the digest even when the ZIP stays unchanged.
   Both retained Version descriptions bind it; the orchestrator Version also binds
   `JudgeTokenNotAfter`, so expiry rotation cannot silently reuse an old version.

4. Review `requirements/day15-deployment-contract.json`. It freezes region `eu-central-1`, profile
   `aioa-day15-deployer`, deployment-role leaf `AIOANonZeroCloudOpsDay15DeploymentRole`, stack
   `aioa-nonzero-cloudops-day15`, change set `day15-reviewed-release`, artifact path
   `day15/reviewed/aioa-lambda.zip`, `CAPABILITY_IAM`, and all required packaging-bucket controls:
   encryption at rest, TLS-only access, versioning, all four public-access blocks, and lifecycle
   expiration no later than three days. Its selected bucket hash, deployment-role ARN hash, and
   reviewed change-set digest deliberately remain null and `BLOCKED` until an authorized operator
   supplies those reviewed bindings. No actual account, bucket, role ARN, or target identifier is
   committed.

5. Create `dist/day15/external-preflight.json` only after an authorized operator has performed the
   separate bounded checks and populated a canonical raw-bindings file outside the repository with
   mode `0600`. The file must identify the correct account; fixed profile, role, stack, change set,
   and artifact path; encrypted/private/TLS-only/versioned short-lifecycle bucket; judge-secret
   create and read authority; exact pre-existing sandbox target/tag/region; sufficient CloudWatch
   evidence; Nova 2 EU profile access; and owned cost notifications. It also binds the reviewed
   change-set digest and IAM capability acknowledgement. The stack never creates a budget or
   guesses a recipient. Thresholds remain USD 10, USD 25, and USD 40.

   A bare boolean file is not evidence. The operator key must contain at least 32 bytes, remain
   outside the repository with mode `0600`, and match the independently reviewed fingerprint in
   `requirements/day15-external-trust-policy.json`. That tracked policy is intentionally
   `BLOCKED` with no fingerprint in this candidate. The schema-v4 HMAC receipt binds the ZIP,
   manifest, source commit, source and rendered templates, configuration digest, generator,
   bounded token expiry, cost policy, trust-policy digest, and SHA-256-only external identities.
   It never contains raw account, profile, role, bucket, secret, target, endpoint, or recipient
   values. `docs/operations/day15-external-bindings.example.json` shows the protected input shape;
   its placeholders are deliberately invalid.

   Once the contract hashes and trusted operator fingerprint have been separately reviewed, create
   the candidate-specific receipt with every explicit confirmation:

   ```bash
   .venv/bin/python scripts/day15/external_preflight_attestation.py \
     --configuration-sha256 '<reviewed-configuration-sha256>' \
     --judge-token-not-after '<reviewed-UTC-expiry>' \
     --attestation-key-file '<protected-key-outside-repository>' \
     --external-bindings-file '<protected-raw-bindings-outside-repository>' \
     --confirm-artifact-bucket-encryption-ready \
     --confirm-artifact-bucket-lifecycle-ready \
     --confirm-artifact-bucket-public-access-block-ready \
     --confirm-artifact-bucket-tls-only-ready \
     --confirm-artifact-bucket-versioning-ready \
     --confirm-artifact-path-ready \
     --confirm-authorized-profile-ready \
     --confirm-authorized-role-ready \
     --confirm-change-set-reviewed-ready \
     --confirm-cloudwatch-sufficient-data-ready \
     --confirm-correct-account-ready \
     --confirm-cost-notification-owned \
     --confirm-iam-capability-acknowledged \
     --confirm-judge-secret-create-ready \
     --confirm-judge-secret-read-ready \
     --confirm-nova-profile-access-ready \
     --confirm-sandbox-region-ready \
     --confirm-sandbox-tag-ready \
     --confirm-sandbox-target-ready \
     --json
   ```

   The generated receipt shape is illustrated in
   `docs/operations/day15-external-preflight.example.json`. The gate requires the same protected key
   through `--external-attestation-key-file`, verifies its pinned fingerprint and HMAC in constant
   time, recomputes every candidate binding, and cross-checks external hashes against the frozen
   deployment contract. A copied, edited, stale, unsigned, arbitrarily keyed, rebound, or manually
   invented receipt fails.

6. Run the complete local gate with the explicit inputs:

   ```bash
   .venv/bin/python scripts/day15/run_day15_gate.py \
     --region eu-central-1 \
     --judge-token-not-after '<reviewed-UTC-expiry>' \
     --lambda-configuration-sha256 '<reviewed-configuration-sha256>' \
     --rendered-template '<reviewed-rendered-template>' \
     --external-attestation-key-file '<protected-key-outside-repository>' \
     --json
   ```

The stable gates are D15-G01 runtime composition, G02 rendered IAM, G03 SDK retry ownership, G04
artifact reproducibility/scans, G05 retained state, G06 region, G07 versions/aliases/rollback, G08
logs/telemetry/cost controls, G09 the single read-only public surface, and G10 external
prerequisites plus token lifetime. `ready_for_deployment` is true only when all ten are `PASS`.
Missing SAM rendering, scanner/container proof, build artifacts, or operator prerequisites stays
visible as `PARTIAL` or `BLOCKED`.

The remaining frozen tools are AWS CLI `2.36.11`, Python `3.12.3`/x86_64, pip `26.2.1`,
pip-audit `2.10.1`, and Podman `4.9.3` with the exact Lambda image digest in the toolchain record.
The ignored local tool environments are conveniences, not evidence; the gate checks the executing
versions and regenerates the relevant proof.

## Staged public ingress

Public ingress is never enabled in the first change set. The first separately reviewed change set
must pass `PublicIngressEnabled=false`; after it completes, verify the deployed numeric versions,
both `live` aliases, configuration digest, judge expiry, all three disabled mutation flags, private
executor isolation, readiness, log retention, and alarms. These are read-only/private checks; they
do not call the model or mutation path.

Only then may a second separately reviewed change set set `PublicIngressEnabled=true`. Its policy
diff must add exactly the two conditioned permissions already frozen in the template: URL invoke
with `FunctionUrlAuthType=NONE`, and function invoke only with `InvokedViaFunctionUrl=true`. It must
add no API Gateway, direct public invoke, approval/resume route, or mutation route.

Rollback and teardown reverse exposure first: remove both public permissions and the Function URL,
verify they are absent, and only then consider aliases, functions, or the rest of the stack. The
retained table is governed by the separate disposition runbook. This document intentionally
contains no deployment command, and no change set was created or executed here.

## Alias-only rollback and reconciliation

Both `live` aliases always point to numeric retained versions. Rollback changes aliases only; it
does not rebuild code or alter the state table. Capture both previously reviewed numeric versions
before deployment.

The default command performs read-only AWS preflight calls: it confirms both named functions belong
to the explicit stack, reads both current `live` aliases, and proves both target versions still
exist. It then emits a canonical plan and SHA-256 for review:

```bash
.venv/bin/python scripts/day15/alias_rollback.py \
  --stack-name '<stack-name>' \
  --orchestrator-function-name '<orchestrator-function-name>' \
  --executor-function-name '<executor-function-name>' \
  --orchestrator-previous-version '<numeric-version>' \
  --executor-previous-version '<numeric-version>' \
  --profile '<authorized-profile>' \
  --region eu-central-1 \
  --json
```

Only after reviewing that exact plan may an authorized operator add both explicit write controls:

```bash
.venv/bin/python scripts/day15/alias_rollback.py \
  --stack-name '<stack-name>' \
  --orchestrator-function-name '<orchestrator-function-name>' \
  --executor-function-name '<executor-function-name>' \
  --orchestrator-previous-version '<numeric-version>' \
  --executor-previous-version '<numeric-version>' \
  --profile '<authorized-profile>' \
  --region eu-central-1 \
  --execute \
  --confirm-plan-sha256 '<reviewed-plan-sha256>' \
  --json
```

The tool strips ambient credential/region selectors, uses only the named profile and region, updates
only pending aliases, and re-reads both aliases. If one update succeeds and the other does not, it
returns `PARTIAL` with `ALIAS_RECONCILIATION_REQUIRED`; rerun the read-only plan, review the new
state, and explicitly execute reconciliation. No live rollback receipt exists in this repository,
and local tooling success does not claim one.

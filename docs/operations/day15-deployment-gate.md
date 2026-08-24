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

   Structural validation is useful without SAM CLI, but the result remains `PARTIAL` when
   `sam validate --lint` cannot run. Never hide that toolchain gap.

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

4. Create `dist/day15/external-preflight.json` only after an authorized operator has verified the
   named profile/role, encrypted private artifact bucket and lifecycle, sandbox scope, dedicated
   judge-secret plan, Bedrock access, and cost-notification ownership. Budget notifications are
   frozen at USD 10, USD 25, and USD 40. No `AWS::Budgets::Budget` resource or notification target
   is created by this stack unless the existing owner and target have first been verified.

   A bare boolean file is not evidence. The attestation is authenticated with an operator-held key
   of at least 32 bytes, stored outside the repository with mode `0600`, and is bound to the ZIP,
   manifest, source commit, raw and rendered templates, configuration digest, generator code, a
   hash of the bounded token expiry, and the exact cost-notification policy: currency `USD` and
   thresholds `[10, 25, 40]`. The closed schema and HMAC cover those values; changing or removing a
   threshold invalidates the receipt even if the altered document is re-signed. The key, expiry,
   resource identifiers, profile, account, bucket, target, endpoint, and notification recipients
   are never written to the receipt or CLI output. After the separate read-only checks, create the
   candidate-specific attestation:

   ```bash
   .venv/bin/python scripts/day15/external_preflight_attestation.py \
     --configuration-sha256 '<reviewed-configuration-sha256>' \
     --judge-token-not-after '<reviewed-UTC-expiry>' \
     --attestation-key-file '<protected-key-outside-repository>' \
     --confirm-artifact-bucket-ready \
     --confirm-authorized-profile-ready \
     --confirm-bedrock-access-ready \
     --confirm-cost-notification-owned \
     --confirm-judge-secret-plan-ready \
     --confirm-sandbox-target-ready \
     --json
   ```

   The closed schema is illustrated in
   `docs/operations/day15-external-preflight.example.json`; placeholders are deliberately invalid.
   The gate requires the same protected key through `--external-attestation-key-file`, verifies the
   HMAC in constant time, and recomputes every binding. A copied, edited, stale, unsigned, rebound,
   or manually invented receipt fails.

5. Run the complete local gate with the explicit inputs:

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

# Non-AWS live demo deployment

Status: `D1.1_TARGET_SELECTED`; live service not yet created.

## Frozen application boundary

The Render deployment builds the existing root `Dockerfile`. The accepted application source is the
merged `main` tree at `4fafed8b1a877e55d96ddd9baea0a737fbeeaa4a`. Deployment-only commits may add
configuration and evidence, but must not change the Dockerfile, packaged source, dependency locks,
runtime contract, or jury runbook without invalidating B5/B6.

The service remains the portable deterministic sandbox:

```text
AIOA_RUNTIME_MODE=portable
AIOA_MODEL_PROVIDER=mock
AIOA_AWS_INTEGRATION_ENABLED=false
AIOA_ALLOWED_EGRESS=none
AIOA_AUTHORITY_MODE=HUMAN_APPROVAL_REQUIRED
```

## Selected target

Render Free Web Service in `frankfurt` is the single selected target. The checked-in Blueprint pins
`plan: free`, disables automatic deployment, uses platform HTTPS, and probes `/ready`. No database,
disk, worker, cron job, custom domain, paid plan, or AWS resource is part of the deployment.

Official provider references checked on 2026-09-02:

- <https://render.com/docs/free>
- <https://render.com/docs/blueprint-spec>
- <https://render.com/docs/docker>
- <https://render.com/docs/health-checks>
- <https://render.com/docs/regions>
- <https://render.com/docs/configure-environment-variables>

## Secret bootstrap

`AIOA_OPERATOR_TOKEN` is declared with `sync: false`; its value must be entered only in the Render
dashboard during the first Blueprint creation. It must be a freshly generated, URL-safe value of at
least 48 characters. It must never be committed, pasted into a terminal transcript, written to a
URL query, or printed in deployment logs.

The deployment command runs as the image's non-root `aioa` user. It creates the canonical token file
with `umask 077`, removes the bootstrap variable before replacing itself with the frozen canonical
process, and fails closed if the secret is absent. The browser UI exchanges the one-time fragment
bootstrap for an `HttpOnly`, same-origin session and immediately removes the fragment from history.

## State and recovery contract

Render Free has an ephemeral filesystem and does not support a persistent disk. The service's
protected file state therefore persists only for the lifetime of a running instance. A restart,
redeploy, or idle spin-down intentionally creates a fresh deterministic demo sandbox. This is a
disclosed demo limitation, not durable production storage.

Evidence needed for the final submission is captured outside the provider after redaction. The D2
restart drill must verify both sides of this contract: restart recovery to healthy/ready service and
expected reset of instance-local demo state.

## CLI acceptance after the human deploys

The provider control plane is not used by the acceptance harness. After the human has created the
reviewed Blueprint, provide only the public origin and an owner-only regular token file:

```bash
export AIOA_PUBLIC_URL="https://<service>.onrender.com"
export AIOA_OPERATOR_TOKEN_FILE="/absolute/path/to/owner-only/operator.token"
.venv/bin/python scripts/operations/run_live_acceptance.py --mode live \
  --receipt .local/live-acceptance/acceptance-receipt.json
```

The token is intentionally unavailable as a CLI argument. The harness rejects non-HTTPS live
origins, loopback confusion, symlinked or group/world-accessible token files, unbounded timeouts,
and non-verifying TLS. Its receipt contains the origin, tested source revision, timestamps, HTTP
status codes, and response hashes; it never contains the token, session cookie, raw request headers,
or raw response headers. `--mode local` applies the same contract to an explicit loopback HTTP
origin for deterministic pre-deployment proof.

## Launch and rollback controls

1. Authenticate to Render; stop for CAPTCHA, 2FA, payment, or legal declarations.
2. Create one Blueprint from `render.yaml` on
   `codex/portable-d1-d2-m1-overnight`.
3. Confirm the only planned resource is a Free Web Service in Frankfurt.
4. Enter the operator token only into the `sync: false` secret prompt.
5. Deploy only after the plan still shows `free` and no card or paid resource.
6. Record service/deployment identifiers, exact Git revision, image/build identity, and public URL.
7. Use Render's recent-deployment rollback for the bounded D2 drill. If unavailable, redeploy the
   recorded exact known-good revision without editing source or bypassing safety controls.

Automatic deployment is disabled. Any later configuration sync or manual deploy requires a new
evidence receipt.

## Rejected targets

- Koyeb has a Free Instance, but its Starter organization requires a valid payment method.
- Railway offers a one-time trial credit without a card, not a durable zero-paid tier.
- Fly.io has no free tier and requires a credit card for organizations.
- Hugging Face Docker Spaces require a paid account plan under the current Spaces rules.

No account or service was spray-created on the rejected providers.

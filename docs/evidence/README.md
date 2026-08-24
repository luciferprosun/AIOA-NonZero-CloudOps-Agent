# Reviewer evidence

The AU-3 manifest maps conservative project claims to the source, tests, gates, and immutable Git snapshot that support them. It is a reviewer index only; runtime policy, typed contracts, durable approval, and the private executor remain the authority boundaries.

## Rebuild and validate

From the repository root in the documented development environment:

```bash
.venv/bin/python scripts/build_reviewer_evidence_manifest.py
.venv/bin/python scripts/build_reviewer_evidence_manifest.py --check
.venv/bin/python scripts/validate_reviewer_evidence_manifest.py
```

The builder is anchored intentionally to L1 commit `fbb536400594306f2bb3abd31c7064a66735c82d`. It does not derive an anchor from the changing `HEAD`, so rebuilding after L2/L3 is byte-for-byte stable and avoids a self-referential commit hash.

## Canonical model

Each claim contains the required `claim_id`, `claim`, `evidence_kind`, `authority_source`, `proof_nodes`, `commit_anchor`, `status`, `scope`, `limitations`, and `hash` fields. Python authority references use `path::symbol`; exact non-Python anchors use `path#text`; a path alone proves a tracked regular file. Pytest proof nodes use their exact `path::test_name`; P0/P1 nodes use exact gate IDs.

Claim hashes are SHA-256 over compact, key-sorted UTF-8 JSON with the derived `hash` removed and set-like source/proof lists sorted. `manifest_hash` covers the normalized complete document except itself. Canonical JSON uses sorted keys, two-space indentation, sorted claims, and one final newline. The Markdown view is generated from the same normalized model.

The validator resolves authority files and Python symbols at each claim's commit, resolves exact pytest nodes, and requires every referenced current source/test blob to remain byte-identical to the reviewed snapshot. It validates gate IDs and Git ancestry, checks the explicitly qualified frozen Phase 1 tag, and requires every prior-art path to remain a tracked regular file with its immutable blob. Runtime one-agent/five-tool facts must also match roots extracted directly from the immutable L1 Git object, so a synchronized five-for-five tool substitution or emptied provenance baseline cannot be regenerated into truth. Nova 2, its runtime region, and exact `strands-agents[otel]==1.53.0` pins are validated independently against frozen expectations.

## Live-proof boundary

Source, static checks, and mocked tests do not prove a live AWS event. The manifest therefore records the live EC2 claim as `NOT_YET_PROVEN` and contains no live receipt. A future positive live claim must use `LIVE_RECEIPT`, reference a separately reviewed and tracked sanitized receipt under `docs/evidence/live-receipts/`, and match its SHA-256.

A receipt has a closed schema: claim binding, exact `ec2:StopInstances` operation and region, distinct nonzero hashed target/request/verification identifiers, stopped observation, `SUCCESS_WITH_EVIDENCE`, explicit UTC event time, operator-attested sanitized-export provenance, the fixed affirmative attestation contract, and `sanitized: true`. The event time must fall deterministically between the L1 snapshot commit and the Git commit that introduced the receipt. Unknown or duplicate fields, noncanonical JSON, contradictory/synthetic attestation, raw provider responses, weak evidence hashes, and privacy material fail validation. Promotion also requires an intentional reviewed builder change; inserting a receipt only into generated JSON fails generator-drift validation.

The validator treats any unreviewed live-mutation statement as receipt-requiring, so relabeling it as a local test cannot bypass the proof boundary. It also rejects local paths, account identifiers, credentials, secret-like material, raw prompts, and private machine metadata.

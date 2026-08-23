# Non-Zero Persistence

The state table uses string `PK` and `SK` keys with no GSI. It stores independently typed execution metadata, idempotency locks, approval records, and append-only provenance events.

## Contracts

- Correlation IDs are generated and validated as RFC 9562 UUIDv7 values. UUIDv4 and malformed identifiers fail explicitly.
- Execution state remains exactly `INIT`, `RUNNING`, `PENDING`, `SUCCESS`, or `FAIL`; a missing lifecycle state is invalid.
- Execution metadata carries UTC creation/update timestamps and a positive version used for optimistic concurrency.
- Idempotency claims are atomic create-only records guarded by `attribute_not_exists(PK)`; a duplicate raises a typed conflict.
- State changes require the expected version and current state. A stale writer cannot silently overwrite newer state.
- Provenance events use ordered keys, immutable contracts, allowlisted attributes, and optional SHA-256 evidence digests. No overwrite or delete API is exposed.
- Approval is a separate typed status: `NOT_REQUIRED`, `PENDING_APPROVAL`, `APPROVED`, or `REJECTED`.

When human approval is required, the explicit mapping is `execution_state=PENDING` plus `approval_status=PENDING_APPROVAL`. Approval is not a sixth execution state.

The adapter uses only item-level DynamoDB operations and has no scan or destructive table operation. Its future IAM policy is restricted to `GetItem`, `PutItem`, and `UpdateItem` on the project state table. Validation uses local fakes; no live DynamoDB write or AWS deployment occurred.

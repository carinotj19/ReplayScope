# Upload validation and worker recovery

ReplayScope v0.7.0 adds defensive limits and recovery facilities without
changing the database schema or invalidating your existing SQLite records.

## Input contract limits

- Maximum body size: Flask's 8 MiB request limit.
- Maximum runs: 2,000 per dataset.
- Maximum trace events: 500 per run.
- Maximum nested JSON depth: 10 levels, measured from the per-run
  `{"metadata": ..., "events": ...}` validation root.
- Maximum nested value nodes: 6,000 per run, combined metadata and events.
- Maximum nested string length: 2,048 characters (event type also <=120).
- Maximum nested object key: 128 characters; maximum keys per object: 2,000.
- Nested numeric values must be finite. CSV column names must be unique.

Violations produce an HTTP 422 upload validation response before storing data.
These limits reduce accidental and malicious resource exhaustion. They do not
replace all upload threat modeling, JSON streaming validation or global
resource quotas.

## Exactly-once processing boundaries

Each `process_upload` invocation claims an upload with a conditional SQL
UPDATE from `queued` or `failed` to `processing`. A concurrently delivered
job sees `processing` and exits; a `ready` upload is not re-imported.

Valid run rows and final upload status commit in one transaction. If a worker
raises an exception while constructing the batch, the transaction rolls back,
leaving no partial new rows. Agent-version upserts use database conflict
handling for SQLite and PostgreSQL and are safe to repeat.

This offers **idempotent application-level processing**, not mathematically
exactly-once execution in all distributed failure scenarios. In particular,
there is no worker lease/fencing token yet.

## Queue retry policy

The Flask upload route passes RQ Retry(max=3, interval=[10,60,180]).
Known input errors are stored as `failed` without raising and do not
consume retries. Unhandled failures mark the upload failed and re-raise, so RQ
can schedule the next attempt.

## Manual recovery

From the project root in PowerShell:

    py -m flask --app replayscope:create_app recover-upload UPLOAD_ID

This command retries failed/queued work inline using the configured database
and file store. It does not require a running Redis service.

If the original worker process crashed while holding `processing`, **confirm
that worker is no longer running** and only then use:

    py -m flask --app replayscope:create_app recover-upload UPLOAD_ID --force-stuck

Do not force recovery of a still-active worker. Neither the database nor RQ
can yet prove a worker is dead from the current upload state alone.

## Further work

- Lease timestamps and fencing tokens for safe automatic stale-job recovery.
- Transactionally coordinated queue/database outbox for enqueue failure.
- Multi-worker race/load testing on PostgreSQL.
- Retention policies, content scanning and storage quotas.
- Operator-only audit logs and job retry history.

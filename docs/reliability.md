# Upload validation and worker recovery

ReplayScope v0.8.0 retains the defensive validation and adds fenced upload
leases. A separate lease table preserves the existing local SQLite uploads.

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

ReplayScope now adds a leased token and a heartbeat while a worker parses an
upload. The write transaction checks that the token is still current and
unexpired under upload-then-lease row locks before inserting runs. A reclaimed
worker cannot commit over a newer worker's state.

This offers **fenced application-level processing**, not a mathematical
exactly-once guarantee across every distributed failure scenario.

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

The new `sweep-stale` command reclaims only expired token-bearing processing
records and fences off old owners. It supports a one-shot run or an independent
watchdog process:

    py -m flask --app replayscope:create_app sweep-stale
    py -m flask --app replayscope:create_app sweep-stale --watch --interval 30

A lease still being renewed is never reclaimed. Historical `processing`
records without any active token still require explicit operator review.
Do not force recovery while an old, unfenced worker might be running.

## Further work

- Add watchdog metrics, failure alerts and systematic lease renewal outage tests.
- Transactionally coordinated queue/database outbox for enqueue failure.
- Multi-worker race/load testing on PostgreSQL.
- Retention policies, content scanning and storage quotas.
- Operator-only audit logs and job retry history.

## Migration and clock assumptions

Existing local SQLite users keep their uploaded rows. The application-factory
`db.create_all()` adds only the new `upload_leases` table. For managed database
installations with `DATABASE_URL`, use the Alembic
`0002_upload_leases` migration with `flask db upgrade`.

Lease expiry is compared using UTC timestamps on the database objects and
application-clock timestamps. All worker/watchdog hosts need reasonably
synchronized clocks (NTP); material clock skew can cause early expiration.
The defaults are 120 seconds per lease and a 20-second heartbeat interval.
The watchdog's `--watch` loop is an independently supervised process, not a
Flask request/background task. It executes recovered jobs inline.

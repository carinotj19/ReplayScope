# ReplayScope roadmap

## Completed: local Flask engineering foundation

- [x] Simulation-agnostic JSON and CSV benchmark schema, parser and validator
- [x] Experiment, upload, agent version and normalized run persistence
- [x] Content-hash deduplication, processing states and upload/summary REST APIs
- [x] Responsive Flask/Jinja dashboard and interactive upload controls
- [x] Scenario-level rates, Wilson intervals, run traces and paired seed/scenario comparisons
- [x] Database migrations and PostgreSQL/Redis infrastructure integration tests in CI
- [x] Optional single-operator authentication, session CSRF, API token access and rate limits
- [x] OpenAPI 3.1 contract and browsable API documentation
- [x] Favicon, package version display and packaged static assets
- [x] Deterministic **synthetic** demo fixtures and non-destructive seed CLI
- [x] Portfolio walkthrough and honest deployment gate checklist

## Next: production robustness

- [x] SQLite/PostgreSQL conflict-safe agent/version registration and per-upload atomic worker claims
- [x] Requeue-safe processing, RQ retries and explicit CLI recovery for stranded uploads
- [x] Time-limited leases, periodic heartbeat renewal and commit-time fencing
- [x] Optional sweep-stale watchdog to safely reclaim expired leases
- [x] PostgreSQL concurrent processing stress test with shared agent-version registration
- [ ] Lease expiry metrics, queuing outbox and robust watchdog observability
- [ ] Structured error handling, logs and query performance measurements
- [x] Bounded nested metadata/event validation and duplicate CSV header rejection
- [ ] Retention controls, schema-level semantic validation and documented export
- [ ] Meaningful paired-comparison statistical uncertainty, evaluated on larger controlled samples

## Before any public launch

- [ ] Choose deployment topology, HTTPS and secret storage
- [ ] Require auth in deployed environments and properly isolate user data
- [ ] Shared rate-limit backing store and safe reverse-proxy configuration
- [ ] Durable upload storage, database backups and migration/restore testing
- [ ] Smoke-test actual deployment end-to-end, not only in GitHub Actions
- [ ] Review accessibility and representative application performance
- [ ] Add approved, clearly labeled demo screenshots and interview walkthrough

See [deployment readiness](deployment-readiness.md). The Docker Compose stack is still **local-only** and does not require installation on the developer's Windows machine for application work.

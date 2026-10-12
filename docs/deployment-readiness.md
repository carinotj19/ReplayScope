# ReplayScope deployment-readiness checklist

**Current state:** GitHub Actions exercises unit tests and PostgreSQL/Redis integration, but passing CI alone does **not** make ReplayScope safe to host on the public Internet.

The local SQLite/demo and Docker Compose configurations are development environments. `compose.yaml` deliberately uses a weak local password and localhost-only port binding. Do not reuse those credentials on a public host.

## Safety gates before sharing a public URL

- [ ] Define the expected audience and threat model: recruiter-only demo, single admin or multi-user service.
- [ ] Require HTTPS, trustworthy reverse-proxy configuration, and secure cookies (`REPLAYSCOPE_SECURE_COOKIE=1` behind HTTPS).
- [ ] Make authentication **mandatory** for any public deployment; current `REPLAYSCOPE_AUTH_ENABLED=0` quick start must not be used publicly.
- [ ] Move secrets into a deployment secret manager and rotate any token exposed during development.
- [ ] Replace in-memory rate limiting with a shared Redis-backed limiter and configure proxy IP handling deliberately.
- [ ] Implement appropriate authorization isolation for multiple users, or explicitly restrict the app to a single administrator.
- [ ] Configure a hardened WSGI server, disable the Flask debugger, use least-privilege execution and enforce request timeouts.
- [ ] Use managed PostgreSQL with applied and reviewed Alembic migrations; confirm backups and restore procedures.
- [ ] Replace local upload storage with a durable shared store if API and worker run on separate hosts; restrict access and define retention/deletion.
- [ ] Evaluate upload threats including oversized/nested metadata, deep event objects, resource exhaustion, content scanning, and safe error responses.
- [x] Add conditional per-upload worker claims, SQLite/PostgreSQL agent-version upsert, and bounded RQ retry policy.
- [ ] Add worker leases/heartbeats, dead-letter review and multi-worker concurrency stress tests before deploying.
- [ ] Add structured logs, traceable request/job IDs, metrics, alerting and a documented incident process.
- [ ] Audit dependencies and license obligations; pin release artifacts and use deployment credentials with minimum permissions.
- [ ] Complete an end-to-end deployment smoke test: login, upload, queue, processing, comparison and logout.
- [ ] Review accessibility and performance under representative data volume; verify screenshots and README match the deployed build.

## What can be demonstrated today

The **local** application already has optional single-admin authentication, signed sessions, CSRF on authenticated browser writes, optional bearer API tokens, rate limits and restrictive browser headers. They show awareness of security fundamentals but **are not complete production controls**.

The existing GitHub Actions pipeline creates PostgreSQL and Redis services for integration testing, which demonstrates the backend architecture even when Docker Desktop is unavailable on the developer's Windows PC.

## A pragmatic release sequence

1. Keep using local SQLite + inline workers for feature and presentation iteration.
2. Add durable demo data and an operations checklist with measured tests.
3. Choose a hosting environment and supported Postgres/Redis services; don't embed secrets in the repo.
4. Implement the missing security gates; validate the deployment with non-sensitive synthetic fixtures.
5. Only then publish a public URL and capture portfolio screenshots.

If a public instance is not justified, a private repository plus a short local demo recording may be a better and safer portfolio artifact.

# ReplayScope roadmap

## Flask backend foundation
- [x] Simulation-independent JSON and CSV benchmark schema
- [x] Experiment, upload, agent version and normalized run storage
- [x] Status tracking, SHA-256 deduplication and worker entry point
- [x] REST API, Pytest and GitHub Actions
- [x] Local upload-to-summary workflow verified on Windows
- [ ] Live Redis/RQ smoke test

## Portfolio dashboard (this branch)
- [x] Responsive Flask/Jinja experiment overview and detail pages
- [x] Experiment creation and JSON/CSV browser uploads
- [x] Scenario-filtered visual comparison of version outcomes
- [x] Paginated run history with per-run failure/metadata/trace inspection
- [x] Upload statuses and HTML smoke tests
- [ ] Browser visual and interaction QA on Windows (user confirmation pending)
- [ ] Charts with richer time-series aggregation

## Reliable backend
- [ ] PostgreSQL, Alembic migrations and safe concurrent upserts
- [ ] Redis/RQ integration tests, retries, structured logs and shared storage
- [ ] Authentication, authorization, CSRF prevention and rate limiting
- [ ] OpenAPI contract and operational documentation

## Fair analysis and portfolio release
- [ ] Paired scenario/seed comparisons with documented uncertainty
- [ ] Failure categories and evidence-based event timelines
- [ ] Docker Compose, accessible deployment, CI/CD and screenshots
- [ ] Architecture review, interview walkthrough and system trade-offs

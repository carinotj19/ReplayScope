# ReplayScope roadmap

## Flask backend foundation
- [x] Simulation-independent JSON and CSV benchmark schema
- [x] Experiment, upload, agent version and normalized run storage
- [x] Status tracking, SHA-256 deduplication and worker entrypoint
- [x] REST API, Pytest and GitHub Actions
- [x] Local upload-to-summary workflow verified on Windows

## Portfolio dashboard
- [x] Responsive Flask/Jinja experiment overview and detail pages
- [x] Experiment creation and JSON/CSV browser uploads
- [x] Scenario-filtered version comparisons
- [x] Run history with failure reasons, metadata and event inspection
- [x] Upload statuses, pagination, browser smoke tests
- [x] User visual confirmation on Windows
- [x] Deterministic paired scenario/seed comparisons with explicit excluded-run counts
- [ ] Confidence intervals for paired deltas, time-series analysis and richer charts

## Managed databases and background workers (this branch)
- [x] Flask-Migrate with reviewed initial Alembic revision
- [x] Local SQLite quick-start compatibility
- [x] PostgreSQL and Redis services in CI
- [x] Redis/RQ worker integration test
- [x] Docker Compose integration stack with persistent database and shared upload storage
- [ ] Check CI results; run Docker Compose on Windows and verify real async imports
- [ ] Production-safe concurrent upserts, retries, structured logs, data retention

## Security and portfolio release
- [x] Opt-in single-operator login and hashed-password verification
- [x] Session CSRF protections, optional bearer API access and 5/min login throttling
- [x] Rate-limited uploads, defensive response headers and accessible sign-in view
- [x] Readability polish for smaller dashboard labels
- [ ] Multi-user authorization, production secrets management and shared Redis rate-limit state
- [x] Version-controlled OpenAPI 3.1 contract, local HTML reference and packaged API docs
- [x] JSON HTTP errors for API routes (404 and oversized payloads)
- [x] Favicon and browser route polish
- [ ] Request timeouts, normalized structured errors and stronger data validation
- [ ] Statistically justified uncertainty for paired score differences and reproducibility checks
- [ ] Deployment review, CI/CD, screenshots and interview documentation

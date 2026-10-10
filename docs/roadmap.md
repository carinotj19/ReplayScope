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
- [ ] More meaningful time-series analysis, paired comparisons and richer charts

## Managed databases and background workers (this branch)
- [x] Flask-Migrate with reviewed initial Alembic revision
- [x] Local SQLite quick-start compatibility
- [x] PostgreSQL and Redis services in CI
- [x] Redis/RQ worker integration test
- [x] Docker Compose integration stack with persistent database and shared upload storage
- [ ] Check CI results; run Docker Compose on Windows and verify real async imports
- [ ] Production-safe concurrent upserts, retries, structured logs, data retention

## Security and portfolio release
- [ ] Authentication/authorization, CSRF defense, rate limits
- [ ] OpenAPI contract and stricter error handling
- [ ] Fair paired scenario/seed comparisons and confidence statements
- [ ] Deployment review, CI/CD, screenshots and interview documentation

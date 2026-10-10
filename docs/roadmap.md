# ReplayScope roadmap

## 1. Flask foundation (this branch)
- [x] Simulator-agnostic JSON and CSV data schema
- [x] Flask application factory, Blueprints and REST API
- [x] Persistent experiments, uploads, agent versions and runs
- [x] SHA-256 deduplication scoped to an experiment
- [x] Inline processing and Redis/RQ queue integration option
- [x] Basic descriptive statistical analysis with scenario slices
- [x] Parser/API automated tests and GitHub Actions CI
- [ ] Verify CI and execute a live Redis/RQ integration smoke test

## 2. Reliable background processing
- [ ] PostgreSQL, Alembic migrations and concurrency-safe upsert
- [ ] Error/retry visibility, structured logs, persistent shared storage
- [ ] Repeatable import/reprocessing benchmarks and OpenAPI contract

## 3. Frontend dashboard
- [ ] Jinja / HTMX interface and Chart.js charts
- [ ] Experiment/version explorer, upload status, trace viewer
- [ ] Filter and compare scenarios and seeds

## 4. Statistical comparisons
- [ ] Paired seed/scenario comparisons with trustworthy effect sizes
- [ ] Error-category breakdown and evidence-backed event timelines
- [ ] Comparison export and validation rules

## 5. Portfolio release
- [ ] Docker Compose, authentication/authorization, deployment and CI/CD
- [ ] End-to-end demo, screenshots, architecture decisions and test coverage summary

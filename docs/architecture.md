# ReplayScope architecture

ReplayScope is a portfolio Flask app with a simulation-independent domain.

## Components

- Flask app factory registers the API and server-rendered dashboard Blueprints.
- Pure-Python ingestion validates JSON/CSV benchmark runs and optional trace events.
- SQLAlchemy stores experiments, uploaded datasets, agent versions and benchmark runs.
- An upload is SHA-256 deduplicated per experiment; source files use generated names.
- Processing runs inline for the simple SQLite demo or via Redis/RQ in Compose.
- Descriptive outcomes, scenario slices, durations, score means and failure labels are exposed through the dashboard and REST API.

## Persistence strategy

The original local SQLite demo is automatically created when DATABASE_URL is absent,
so existing users do not lose their dashboard or historical local tests.

Managed DBs (DATABASE_URL set) default to AUTO_CREATE_DB=0, and must run
an explicit Alembic migration before servicing requests.

Migration 0001_initial creates experiments, agent_versions, replay_uploads,
benchmark_runs, indexes and unique constraints.

Do not run the initial migration directly over a SQLite database created by
the old db.create_all path. A production migration of existing data requires
a deliberate schema verification/stamp or a data transfer plan.

## Queue execution

1. Flask validates and stores the source file.
2. In RQ mode, it enqueues replayscope.jobs.process_upload by upload ID.
3. An RQ worker loads the same source path using shared UPLOAD_DIR and DATABASE_URL.
4. The worker updates upload status, persists normalized runs, and marks ready.
5. Flask polls the status and shows results; errors are surfaced in the UI.

Compose shares a named upload volume between API and worker and a PostgreSQL DB
between services. CI runs a dedicated PostgreSQL migration/ingestion test and
an actual Redis queue + SimpleWorker smoke test.

## Rate interpretation

Game win rate uses win/loss/draw; task success rate uses success/failure.
Wilson intervals assume independent observations. Scores are not normalized,
so cross-scenario means may be misleading. The dashboard does not make causal
claims or infer failure root causes.

## Known gaps

This is a local portfolio prototype. Missing: auth, CSRF protection, rate
limits, safe file retention policy, concurrency-safe upsert for registering
an AgentVersion simultaneously, RQ retry policies and structured logs.
The Compose file deliberately binds the web server only to localhost.

## Version pairing

A direct version comparison uses normalized runs from **one experiment** and
**two versions of the same agent**. A match requires identical scenario and
nonempty seed values on both sides, with exactly one run for each key. Duplicate
keys and missing seeds are excluded and counted. Only ready uploads are included.

The result reports candidate-minus-baseline score deltas, descriptive
mean/median, counts of positive/zero/negative deltas, per-scenario aggregates,
and up to 50 example pairs. The full set of matched pairs contributes to the
aggregate even when detail rows are truncated. Durations are compared only
when both paired runs recorded them.

This avoids pairing unrelated samples but **does not** alone establish causal
improvements or statistical significance. Score direction/scale must be
consistent; use the scenario filter to avoid mixing incompatible metrics.

## Security boundary (local prototype)

Security is optional for localhost development to preserve the simple demo.
REPLAYSCOPE_AUTH_ENABLED=1 enables the single-operator mode; startup refuses to
run without a nontrivial SECRET_KEY and an administrator password hash.

- Signed HttpOnly SameSite=Lax session cookies protect the dashboard.
- POST/PUT/PATCH/DELETE with a browser session require an unpredictable CSRF
  token. The frontend sends it as X-CSRF-Token.
- Optional bearer tokens work ONLY on /api/v1 resources and do not depend on
  browser sessions or CSRF; clients must protect that credential.
- Login and upload endpoints have per-IP rate limits (5/minute and 30/hour),
  scoped only to enabled auth mode. Development storage is memory://; real
  multi-process deployments need shared Redis rate-limit storage.
- CSP, X-Frame-Options, nosniff and restrictive browser permissions are set.
  The CSP allows inline styles for existing result-bar widths; script sources
  are restricted to same-origin code. No inline JavaScript handlers remain.
- Passwords are checked against a hash supplied through the environment.
  The app does not implement user registration or multi-user permissions.

This does not imply readiness for public Internet hosting. It still needs
HTTPS termination, secure cookie configuration, secrets storage, stronger
operational controls, dependency monitoring and deployment review.

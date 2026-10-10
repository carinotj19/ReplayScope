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

# ReplayScope

**ReplayScope** is a Python/Flask dashboard for benchmarking AI-agent behavior: experiments, agent versions, JSON/CSV imports, descriptive outcome rates, and per-run trace events. It is simulation-independent and ships with illustrative sample data.

**Status:** portfolio prototype. Includes a responsive Jinja dashboard, REST API, SQLAlchemy persistence, Alembic schema migrations for managed installations, an optional Redis/RQ worker, automated tests and CI. It is not yet secured for public deployment.

## Run the existing Windows demo (SQLite, no Docker required)

    cd E:\Repo\ReplayScope
    .\.venv\Scripts\Activate.ps1
    python -m pip install -e ".[dev]"
    python -m pytest -q --basetemp="$env:LOCALAPPDATA\pytest-replayscope"
    python -m flask --app replayscope:create_app run --debug

Open http://127.0.0.1:5000/ . Existing local SQLite datasets and experiments are preserved.

From the browser: create an experiment, upload examples/benchmark.json or
examples/benchmark.csv, filter by scenario, inspect runs, and select **Paired comparison** on an experiment.
JSON events provide simple per-run trace inspection.

## Full integration stack (requires Docker Desktop and Compose)

From the repository root:

    docker compose up --build

Open http://127.0.0.1:8000/ . Compose starts PostgreSQL, Redis, the Flask/Gunicorn
API, and an RQ worker. The API applies Alembic migrations to the initially empty
PostgreSQL database before the worker starts. Uploaded files are stored in a shared
named Docker volume. Docker data is separate from the earlier local SQLite demo.

To stop, press Ctrl+C or run:

    docker compose down

The volumes persist. Use docker compose down -v only if you intentionally want to
DELETE the Compose database and uploads.

The Compose password is intentionally weak and hard-coded for local development:
DO NOT expose the containers publicly or reuse this setup in production.

## Managed DB migrations

When DATABASE_URL is provided, ReplayScope defaults to AUTO_CREATE_DB=0 and does
not silently create tables. For an EMPTY managed PostgreSQL database:

    python -m flask --app replayscope:create_app db upgrade

The SQLite quick-start still creates its schema automatically if DATABASE_URL is
unset. Avoid applying the initial schema migration on top of an already-populated
SQLite database, or you will encounter existing-table conflicts.

## API

| Method | Path | Description |
| --- | --- | --- |
| GET | /health | Service health |
| GET, POST | /api/v1/experiments | Experiments |
| GET | /api/v1/agent-versions | Versions created during ingestion |
| POST | /api/v1/uploads | Multipart file + experiment_id |
| GET | /api/v1/uploads/{id} | Async processing state |
| GET | /api/v1/experiments/{id}/runs | Paginated runs with filters |
| GET | /api/v1/experiments/{id}/summary | Agent/version and scenario summaries |
| GET | /api/v1/experiments/{id}/compare | Matched seed/scenario score differences (`baseline_id`, `candidate_id`, optional `scenario`) |

Input records require agent, version, scenario, outcome (win/loss/draw or
success/failure), and finite score. Optional fields: seed, duration_ms,
failure_reason, metadata and events (typed JSON event objects).

Limits: 8 MiB/file, 2,000 runs/file, 500 events/run; duplicate file bytes
within an experiment are deduplicated. Game win and task success rates are
calculated separately, with Wilson 95% intervals. Do not infer significance
from small or unmatched sample runs.

## Paired score comparison

Open an experiment's **Paired comparison** screen. Choose a baseline and
candidate version of the **same agent**. ReplayScope matches records only when
they are in the same experiment, with identical `scenario` and nonempty `seed`
values, and exactly one run per side for each key. Repeated keys are excluded,
not arbitrarily combined. Missing-seed and unmatched-key counts are displayed.

For each pair, **score delta = candidate score minus baseline score**. The UI
shows mean and median deltas, counts of higher/equal/lower candidate scores,
per-scenario breakdowns and a sample of paired rows. The calculation assumes
higher score is desirable; it does not infer causal improvement or statistical
significance. Mixed scenarios can have incompatible score scales; filter to a
single scenario when interpreting score differences.

Example direct API request (experiment ID 1, agent-version IDs 1 and 2):

    Invoke-RestMethod "http://127.0.0.1:5000/api/v1/experiments/1/compare?baseline_id=1&candidate_id=2"

Existing sample `examples/benchmark.json` includes matched Pathfinder seeds,
so no new dataset is needed to explore the feature.

See docs/architecture.md and docs/roadmap.md.

**Warning:** No user auth, CSRF defense, public-hosting hardening or per-user
quotas are implemented. Keep this version on localhost.

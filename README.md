# ReplayScope

**ReplayScope** is a Python/Flask dashboard for benchmarking AI-agent behavior: experiments, agent versions, JSON/CSV imports, descriptive outcome rates, and per-run trace events. It is simulation-independent and ships with illustrative sample data.

**Status:** portfolio prototype. Includes a responsive Jinja dashboard, REST API, SQLAlchemy persistence, Alembic schema migrations for managed installations, an optional Redis/RQ worker, automated tests and CI. The optional single-operator protected mode adds login, CSRF protection, API token access, rate limits and browser security headers. This is not yet a production multi-user application.

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

## Enable protected single-operator mode (optional)

The normal localhost demo requires **no configuration** and keeps using your
existing SQLite data. For an opt-in protected demo in Windows PowerShell:

    $env:REPLAYSCOPE_SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(48))"
    $env:REPLAYSCOPE_ADMIN_PASSWORD_HASH = python -c "import getpass; from werkzeug.security import generate_password_hash; print(generate_password_hash(getpass.getpass('New admin password: ')))"
    $env:REPLAYSCOPE_AUTH_ENABLED = "1"
    python -m flask --app replayscope:create_app run --debug

Open http://127.0.0.1:5000/ — the dashboard now redirects to a sign-in page.
The password is NOT stored in the repository or in SQLite. Configuration above
exists only for the current PowerShell session. Keep the same
REPLAYSCOPE_SECRET_KEY across restarts to preserve login sessions. Restarting
with a different key will sign existing sessions out. Disable protected mode
again with:

    Remove-Item Env:\REPLAYSCOPE_AUTH_ENABLED
    Remove-Item Env:\REPLAYSCOPE_ADMIN_PASSWORD_HASH
    Remove-Item Env:\REPLAYSCOPE_SECRET_KEY

With protected mode enabled, cookie-session API writes require the page's
CSRF token in the X-CSRF-Token header; the dashboard adds this automatically.
For programmatic clients, set REPLAYSCOPE_API_TOKEN to a long random value
before startup and send Authorization: Bearer <token>. Bearer credentials
authorize API routes only, not the browser dashboard. See
[the security guide](docs/security.md) for important limitations.

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

**Warning:** Authentication is off by default for the convenient localhost demo. Protected mode is single-operator only. Do not expose this version to the public Internet; HTTPS, multi-user authorization, secrets management, central rate-limit storage, auditing, and further deployment safeguards require additional work.

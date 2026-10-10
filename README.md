# ReplayScope

ReplayScope is a Flask web app for exploring AI-agent benchmark data: **experiments, agent versions, JSON/CSV ingestion, outcome statistics, and per-run trace events**. It is simulation-independent, and its supplied data is illustrative.

**Status:** local portfolio prototype with a responsive server-rendered dashboard, REST API, database persistence, Redis/RQ optional workers, Pytest and GitHub Actions. Authentication, production migrations/storage and deployment are not yet implemented.

## Run locally (Windows PowerShell)

    py -3 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install -e ".[dev]"
    python -m pytest -q --basetemp="$env:LOCALAPPDATA\pytest-replayscope"
    flask --app replayscope:create_app run --debug

Open **http://127.0.0.1:5000/** to see the dashboard.

From the dashboard:
1. Create an experiment.
2. Open the experiment, choose Import dataset, and upload examples/benchmark.json or examples/benchmark.csv.
3. Review agent/version outcome rates and per-run traces. Use the scenario selector to narrow comparisons.
4. Expand Inspect on a run to see failure reasons, metadata and trace events.

You can also exercise the JSON API:

    $experiment = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/v1/experiments -ContentType 'application/json' -Body '{"name":"API demo"}'
    curl.exe -X POST http://127.0.0.1:5000/api/v1/uploads -F "experiment_id=$($experiment.id)" -F "file=@examples/benchmark.json"
    Invoke-RestMethod "http://127.0.0.1:5000/api/v1/experiments/$($experiment.id)/summary"

## Technology

- Python 3.11+, Flask app factory and separate API/dashboard Blueprints
- Jinja2, accessible semantic HTML, responsive CSS, lightweight vanilla JS
- Flask-SQLAlchemy (local SQLite default; PostgreSQL support planned)
- Optional Redis/RQ job worker, with inline fallback for simple demos
- Pytest, GitHub Actions CI and sample benchmark datasets

## REST API

| Method | Endpoint | Role |
| --- | --- | --- |
| GET | /health | Basic health |
| GET, POST | /api/v1/experiments | List/create experiments |
| GET | /api/v1/agent-versions | Agent versions registered through ingestion |
| POST | /api/v1/uploads | Multipart JSON/CSV file + experiment_id |
| GET | /api/v1/uploads/{id} | Processing status and row count |
| GET | /api/v1/experiments/{id}/runs | Paginated runs, optional scenario and agent_version_id filters |
| GET | /api/v1/experiments/{id}/summary | Grouped version/scenario statistics, optional scenario filter |

## Input format

JSON accepts a list or an object containing runs; CSV accepts one run per row. Each record requires agent, version, scenario, outcome and score. Outcomes are win/loss/draw for competitive benchmarks or success/failure for task benchmarks. Scores must be finite.

Optional: seed (string or integer), duration_ms (nonnegative finite number), failure_reason (string), metadata (JSON object), events (JSON array of objects with a type string). CSV supports scalar fields only.

Current limits: 8 MiB, 2,000 runs per file, and 500 trace events per run. Identical file bytes inside the same experiment are deduplicated.

**Game win rate** = wins / (wins + losses + draws).
**Task success rate** = successes / (successes + failures).
They are reported separately with raw counts and Wilson 95% intervals. Scores should only be compared across compatible scenarios; sample datasets do not establish statistically significant differences.

## Redis / RQ (optional)

To enable queue processing, run a Redis server, set PROCESSING_MODE=rq and REDIS_URL, and share DATABASE_URL plus UPLOAD_DIR between the API and worker. Then run:

    rq worker replayscope --url redis://localhost:6379/0

**Security caveat:** This is a local prototype. The current API has no user authentication, authorization, CSRF defenses, or rate limits. Do not expose it to the public Internet as-is. PostgreSQL migrations, structured operational logging, secure uploads/retention and integration checks are future work.

See docs/architecture.md and docs/roadmap.md.

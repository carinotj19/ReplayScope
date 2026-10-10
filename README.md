# ReplayScope

ReplayScope is a Python/Flask backend for ingesting **simulation and AI-agent benchmark results**, tracking agent versions, and comparing experiments. It is deliberately simulation-independent: no external competition API, active simulation engine, or trained model is necessary.

**Status:** portfolio foundation — structured JSON/CSV ingestion, versioned REST API, SQLAlchemy persistence, Redis/RQ option, descriptive statistics, tests and CI. Dashboard, authentication, migrations and production hosting are subsequent milestones.

## Run locally (Windows PowerShell)

    py -3 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install -e ".[dev]"
    flask --app replayscope:create_app run --debug

Run the tests with:

    python -m pytest -q

## Demo workflow

Create an experiment, then upload the included sample data:

    $experiment = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/v1/experiments -ContentType 'application/json' -Body '{"name":"Portfolio demo"}'
    curl.exe -X POST http://127.0.0.1:5000/api/v1/uploads -F "experiment_id=$($experiment.id)" -F "file=@examples/benchmark.json"
    Invoke-RestMethod "http://127.0.0.1:5000/api/v1/experiments/$($experiment.id)/summary"

The example data is **illustrative**, not a claim of real experiment performance. A CSV example is also provided.

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

## Dataset contract

JSON accepts a list of runs or an object with a runs array; CSV accepts one run per row. Each record requires the following keys:

- agent: nonempty name
- version: nonempty version label
- scenario: task / environment / test-case name
- outcome: win, loss, draw, success or failure
- score: finite number

Optional: seed (string or integer), duration_ms (nonnegative finite number), failure_reason (string), metadata (JSON object), events (array of JSON objects each including a type string). CSV supports scalar fields only; JSON supports metadata and events.

Current limits: 8 MiB per upload, 2,000 runs per file and 500 events per run. Duplicate file bytes within an experiment return the existing upload record.

**Game win rate** = wins / (wins + losses + draws). **Task success rate** = successes / (successes + failures). They are reported separately, with the underlying counts and Wilson 95% intervals. Scores are unitless and should only be compared between compatible scenarios. Failure reasons are user-provided labels, not inferred causes.

## Async option

The default uses inline processing so the demo works without Redis. For a Redis/RQ worker, set PROCESSING_MODE=rq and REDIS_URL=redis://localhost:6379/0, and set DATABASE_URL and UPLOAD_DIR to shared locations in both API and worker environments. Then start:

    rq worker replayscope --url redis://localhost:6379/0

A Redis server must be running. Local SQLite and disk storage are for development only. Do not deploy this version on a public URL without authentication, safe migrations and production storage protections.

See docs/architecture.md and docs/roadmap.md.

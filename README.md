# ReplayScope

**Observe, benchmark and compare AI-agent runs.** ReplayScope is a simulator-independent Python/Flask portfolio project that ingests benchmark datasets, stores normalized runs, and makes performance comparisons inspectable through a web dashboard and REST API.

> **Project status:** A functioning **local portfolio prototype**, not a public SaaS product. Data supplied by the demo generator is explicitly **synthetic**. Public deployment needs the additional safeguards in [the readiness checklist](docs/deployment-readiness.md).

## What you can do

- **Organize experiments** and track named agent versions.
- **Import JSON or CSV** datasets with validation and status tracking.
- **Compare outcomes** by agent version and scenario, with separate win and task-success rates and descriptive Wilson intervals.
- **Inspect run traces**, metadata, durations and reported failure reasons.
- **Pair runs fairly** using identical scenario/seed values; exclude unmatched or duplicated keys rather than manufacturing comparisons.
- **Explore a documented API** at `/docs` and its [OpenAPI 3.1 contract](src/replayscope/openapi.json).
- **Run two reproducible synthetic demos** using a single CLI command.

**No live AI model, simulation engine, external API or Docker installation is required for the local demo.**

## Five-minute demo on Windows PowerShell

Requires Python 3.11+ and Git. From your project folder:

```powershell
cd E:\Repo\ReplayScope
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -e ".[dev]"

# Preview the synthetic data. No data is written by this command.
py -m flask --app replayscope:create_app seed-demo --dry-run

# Add two labeled synthetic experiments; safe to rerun.
py -m flask --app replayscope:create_app seed-demo

# Start the dashboard.
py -m flask --app replayscope:create_app run --debug
```

Open **http://127.0.0.1:5000/**. Your existing local SQLite database is preserved. The sample experiments have `SYNTHETIC DEMO` in their names and will appear next to any workspaces you already created.

If the virtual environment already exists, skip its creation and just activate it. If Windows does not recognize `py` with an active environment, use `.\.venv\Scripts\python.exe -m ...` instead to target the virtual-environment interpreter explicitly.

### Guided walkthrough

1. Open **SYNTHETIC DEMO — Navigation Trials**. Explore 96 synthetic navigation task runs over three difficulties, two versions and identical seeds.
2. Filter the version comparison by `maze-hard` and inspect a run's typed trace events and reported failure reason.
3. Open **Paired comparison**, select Navigator `baseline` and `candidate`, and examine paired score deltas, matching coverage and excluded-run counts.
4. Open **SYNTHETIC DEMO — Arena Trials** for 48 synthetic competitive outcomes, which use *game win rate* instead of task-success rate.
5. Open **API reference** in the sidebar to inspect parameters, response codes and the underlying OpenAPI JSON.

The generator uses deterministic arithmetic, **not** a learned policy or an experimental simulation. Its results are only meant to exercise the product consistently. See [the demo walkthrough](docs/portfolio-demo.md) for exact counts and explanations.

## Architecture

```text
           Browser: Flask/Jinja templates + vanilla JS
                               |
  JSON/CSV uploads --- Flask REST API /api/v1
                               |
                  Validation + SHA-256 dedupe
                               |
                         Upload record
                               |
             Inline processor or Redis/RQ worker
                               |
                SQLAlchemy benchmark runs
                               |
          Scenario analytics + exact seed matching
                               |
              Dashboard + documented API
```

| Layer | Technology / responsibility |
| --- | --- |
| Web UI | Flask + Jinja2 templates, responsive CSS, small vanilla-JS enhancements |
| API | Flask application factory, Blueprints, versioned JSON routes, OpenAPI 3.1 |
| Data validation | Pure-Python, framework-independent JSON/CSV parser |
| Persistence | SQLAlchemy models; local SQLite or PostgreSQL with Alembic migrations |
| Background processing | Redis/RQ worker mode; synchronous mode for simple local testing |
| Security | Optional single-operator login, CSRF, API bearer tokens, rate limits and defensive headers |
| Quality | Pytest, GitHub Actions unit/infrastructure jobs, wheel packaging checks |

**What the numbers mean:** game win rate = wins / (wins + losses + draws); task success rate = successes / (successes + failures). Seed-matched score differences use candidate minus baseline and exclude ambiguous keys. Wilson intervals describe individual rates; **none of these figures alone proves a causal improvement or statistical significance**. Scores from incompatible scenarios should not be averaged for decisions.

## Test the application

```powershell
py -m pytest -q --basetemp="$env:LOCALAPPDATA\pytest-replayscope"
```

The two PostgreSQL/Redis integration tests are intentionally skipped if those services aren't configured on your computer. GitHub Actions runs them using service containers.

For API work, see `http://127.0.0.1:5000/docs` and the route `/api/v1/openapi.json`. A small hand-editable input example is in [examples/benchmark.json](examples/benchmark.json), with a [CSV equivalent](examples/benchmark.csv).

## Authentication and local operation

The localhost quick start intentionally starts in **LOCAL DEMO** mode with authentication disabled. This is suitable only for a trusted local development environment.

For an opt-in protected session, stop Flask and run the following commands in the same PowerShell window:

```powershell
$env:REPLAYSCOPE_SECRET_KEY = py -c "import secrets; print(secrets.token_urlsafe(48))"
$env:REPLAYSCOPE_ADMIN_PASSWORD_HASH = py -c "import getpass; from werkzeug.security import generate_password_hash; print(generate_password_hash(getpass.getpass('New admin password: ')))"
$env:REPLAYSCOPE_AUTH_ENABLED = "1"
py -m flask --app replayscope:create_app run --debug
```

These environment variables are session-scoped, and the administrator password is not stored in the repository. See [the security guide](docs/security.md) for CSRF, API-token usage, and deployment limitations.

## Managed database and queue

For a **new empty** database with `DATABASE_URL`, use `py -m flask --app replayscope:create_app db upgrade` before starting the server. Do not apply the initial Alembic schema-creation migration directly over a pre-existing SQLite database that already has tables.

An optional `compose.yaml` starts PostgreSQL, Redis, Flask/Gunicorn and a shared-file RQ worker in a localhost-only development stack. Docker is **not required** for the local demo. Named volumes persist unless explicitly deleted.

Do not expose the existing Docker example on the public Internet: its credentials are for local testing only.

## Engineering documentation

- [Portfolio demo walkthrough](docs/portfolio-demo.md) — a repeatable feature tour suitable for interviews.
- [Architecture and tradeoffs](docs/architecture.md) — domain model, ingestion boundaries, rate interpretation and current limitations.
- [Deployment readiness](docs/deployment-readiness.md) — the checks still needed before publishing a live URL.
- [Security configuration](docs/security.md) — opt-in single-admin behavior and known gaps.
- [Development roadmap](docs/roadmap.md) — completed and planned work.

ReplayScope remains under active development. Avoid describing it as production-ready or claiming the synthetic benchmark results reflect real AI-agent performance.

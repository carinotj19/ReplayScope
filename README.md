# ReplayScope

**A better way to look at AI agent benchmark runs.**

Benchmarking an agent is one thing. Figuring out *what actually changed* between versions is another.

I built ReplayScope to make that second part easier. Drop in JSON or CSV results, browse individual runs, look at performance across scenarios, and compare two versions without digging through raw logs.

It's a Python/Flask project with a simple web dashboard and REST API. You can run the whole thing locally; no AI model, simulator, or Docker setup is needed to try it.

## What you can do

- **Keep experiments organized.** Group benchmark runs by experiment, agent, and version.
- **Explore the results.** See scores, win and success rates, run durations, failure reasons, and event traces.
- **Compare versions.** Match runs using the same scenario and seed, then inspect score differences side by side.
- **Bring your own data.** Import JSON or CSV files, with validation, upload status tracking, and duplicate detection.
- **Use the API.** Every core workflow is available through a Flask REST API, with an [OpenAPI reference](src/replayscope/openapi.json).

The comparison view deliberately excludes missing or ambiguous seed matches. The numbers are descriptive, not proof that one agent is statistically better than another.

## Getting started

You'll need **Python 3.11+** and Git. These commands are for Windows PowerShell:

```powershell
git clone https://github.com/carinotj19/ReplayScope.git
cd ReplayScope

py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -e ".[dev]"

# Add sample data so there's something to explore.
py -m flask --app replayscope:create_app seed-demo

# Start the app.
py -m flask --app replayscope:create_app run --debug
```

Then open **http://127.0.0.1:5000**.

If you're already working in this repository, just activate your existing `.venv` instead of creating a new one. ReplayScope uses SQLite by default and keeps its data between runs.

### Try the sample experiments

The `seed-demo` command creates two clearly labeled **synthetic** datasets:

| Experiment | What's included |
| --- | --- |
| Navigation Trials | 96 runs across three maze scenarios, with baseline and candidate versions |
| Arena Trials | 48 runs across two arenas, using win/loss/draw outcomes |

Start with Navigation Trials, choose the two versions in **Paired comparison**, and look at the 48 matched scenario/seed pairs. You can also filter by scenario or open individual runs to inspect their event traces.

These datasets are generated examples, not results from a trained agent. They're just there to make the app easy to explore. Running `seed-demo` again won't duplicate them.

There's a more detailed [demo walkthrough](docs/portfolio-demo.md) if you'd like to follow along.

## How it's built

I kept the UI lightweight and put most of the work in the Python backend.

| Part | Stack |
| --- | --- |
| Web app | Flask, Jinja2, vanilla JavaScript, CSS |
| Database | SQLAlchemy + SQLite locally, PostgreSQL as an option |
| Background jobs | Redis and RQ (optional for local use) |
| Migrations | Alembic / Flask-Migrate |
| Tests | Pytest + GitHub Actions |
| API | Flask REST endpoints + OpenAPI 3.1 |

A dataset goes through validation and SHA-256 duplicate checking, then gets stored as normalized benchmark runs. From there, the dashboard and API build the summaries and version comparisons.

For larger setups, ReplayScope also supports queued processing, retry handling, worker heartbeats, and stale-job recovery. The local demo simply processes uploads inline.

The implementation details are in the [architecture notes](docs/architecture.md) and [reliability guide](docs/reliability.md).

## Working with the API

Start the app and visit **[/docs](http://127.0.0.1:5000/docs)** for the browsable API reference, or **[/api/v1/openapi.json](http://127.0.0.1:5000/api/v1/openapi.json)** for the OpenAPI spec.

A couple of useful routes:

```text
GET  /api/v1/experiments
POST /api/v1/experiments
POST /api/v1/uploads
GET  /api/v1/experiments/{id}/runs
GET  /api/v1/experiments/{id}/summary
GET  /api/v1/experiments/{id}/compare
```

Want to try your own dataset? Start with [benchmark.json](examples/benchmark.json) or [benchmark.csv](examples/benchmark.csv).

## Running the tests

```powershell
py -m pytest -q --basetemp="$env:LOCALAPPDATA\pytest-replayscope"
py scripts/release_audit.py
```

PostgreSQL and Redis integration tests run in GitHub Actions. Without those services configured locally, the corresponding tests are skipped.

## A note on the project

**ReplayScope v1.0.0 is a finished local portfolio project**, not a hosted product. It includes an optional single-admin login, but the default local demo runs without authentication. Don't expose that demo server or the development Docker Compose configuration to the public internet.

I wanted the project to focus on the parts that are interesting to build and reason about: data validation, experiment design, comparing runs fairly, database transactions, and what happens when a background worker fails.

If you're curious about the tradeoffs or limitations, I've written them down instead of trying to hide them:

- [Release notes](docs/release-v1.md)
- [Security notes](docs/security.md)
- [Deployment checklist](docs/deployment-readiness.md)

---
*Built with Python and Flask. Benchmark examples are synthetic.*

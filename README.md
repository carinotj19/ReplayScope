# ReplayScope

ReplayScope is a Python/Flask platform for ingesting AI-agent match replays, tracking experiments, and analyzing results. Its first adapter targets Kaggle Orbit Wars (2P and 4P).

Status: v0.1 API foundation on a feature branch, pending CI and real-replay verification.

## Stack

Python 3.11+, Flask application factory, Flask-SQLAlchemy, SQLite for local development, Redis/RQ job processing, Pytest, GitHub Actions. PostgreSQL and server-rendered analytics dashboards are planned.

## Run locally

Create and activate a virtual environment, then run:

    python -m pip install -e ".[dev]"
    flask --app replayscope:create_app run --debug

On Windows PowerShell the activation command is:

    .\.venv\Scripts\Activate.ps1

Default processing is inline for a zero-infrastructure demo. To use Redis/RQ instead, set REPLAYSCOPE_JOBS=rq and REDIS_URL=redis://localhost:6379/0 in both the Flask and worker environments, then run:

    rq worker replay-analysis --url redis://localhost:6379/0

Redis must be started separately. The API and worker must share the same DATABASE_URL and instance upload directory. The default SQLite setup is intended for a single-machine local demo.

## API

- GET /health
- POST /api/agent-versions with JSON name and version
- GET /api/agent-versions
- POST /api/experiments with JSON name
- GET /api/experiments
- POST /api/replays as multipart file (.json), experiment_id, agent_version_id, player_slot
- GET /api/replays/{id}
- GET /api/experiments/{id}/summary

Example PowerShell requests:

    $agent = Invoke-RestMethod -Method Post -Uri http://localhost:5000/api/agent-versions -ContentType 'application/json' -Body '{"name":"OrbitBot","version":"v2"}'
    $exp = Invoke-RestMethod -Method Post -Uri http://localhost:5000/api/experiments -ContentType 'application/json' -Body '{"name":"Baseline"}'
    curl.exe -X POST http://localhost:5000/api/replays -F "file=@C:\path\episode.json" -F "experiment_id=$($exp.id)" -F "agent_version_id=$($agent.id)" -F "player_slot=0"

Run automated tests:

    python -m pytest -q

Current replay outputs: final ship score, rank, outcome, high-production-loss count, production/ship timeline, turn milestones and descriptive signals. Experiment summaries include mode-specific win rate and Wilson 95% intervals.

This release has no user authentication and initializes its development database automatically. Do not deploy publicly without production hardening. See docs/architecture.md and docs/roadmap.md.

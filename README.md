# ReplayScope

ReplayScope is an open-source-friendly AI-agent replay analysis and benchmarking platform, built with Python and Flask.

**Purpose:** ingest match replays, track agent versions and experiments, calculate reproducible performance metrics, and investigate recurring failure patterns.

Orbit Wars (Kaggle) is the first supported domain. The architecture will use replay format adapters so other simulations can be supported later.

## Planned capabilities

- Replay uploads with validation, deduplication and traceable processing status
- Asynchronous analysis through Redis/RQ
- Agent version and experiment tracking
- Win rate, final score, production and turn-by-turn comparisons
- Confidence intervals and clear sample-size disclosures
- Replay-derived diagnostic signals (not unsupported causal claims)
- Flask REST API, PostgreSQL support, tests, CI and deployment documentation

## Build order

1. Flask API and Orbit Wars ingestion vertical slice
2. Persistent experiment analytics and robust processing jobs
3. Dashboard and timeline visualizations
4. Comparison statistics and failure-pattern explorer
5. Deployment, authentication, observability and extensible adapters

> Development status: initial planning/bootstrap. See the upcoming feature branch for the working foundation.

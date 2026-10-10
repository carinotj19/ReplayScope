# ReplayScope architecture

A portfolio Flask app with a **simulation-independent domain**.

Flow:
1. Flask API accepts structured JSON or CSV and experiment reference.
2. Framework-independent parser validates each run and optional trace events.
3. Upload bytes are stored with a generated filename and deduplicated by SHA-256 within the experiment.
4. SQLAlchemy records queued / processing / ready / failed job states.
5. Inline or Redis/RQ processing turns input into normalized benchmark_runs and agent_versions.
6. Aggregations provide per-version, per-scenario outcomes, mean score, mean duration, failure labels and rate intervals.

Models:
- Experiment: named set of benchmark runs
- ReplayUpload: immutable source upload, hash, status, processing details
- AgentVersion: name/version pair
- BenchmarkRun: scenario, optional seed, outcome, score, duration, failure reason, metadata and optional trace events

**Separation of concerns:** API and persistence stay game-agnostic. JSON events retain simulation trace information without requiring special treatment of planets, fleets or rules from any particular game.

Rates:
- Game win rate uses only game outcomes win/loss/draw.
- Task success rate uses only task outcomes success/failure.
- Wilson confidence intervals are descriptive and assume independent runs. Comparing matched seeds or scenario distributions requires a separate analysis.

Current constraints:
- Database creation during app startup is only suitable for development; replace with Alembic.
- Authentication/authorization, rate limiting, retention, object storage, detailed event schema, audit logging and background retry policies are not yet implemented.
- The worker and API must share database and upload storage. Docker/Redis end-to-end tests are future work.
- High-concurrency first-time agent registration needs DB-safe conflict retry/upsert.
- No causal diagnosis or statistically valid A/B claim is made by the current summaries.

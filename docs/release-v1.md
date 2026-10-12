# ReplayScope v1.0.0 — Local portfolio release

## Release classification

**Local portfolio MVP.** This version is intended to demonstrate Flask backend,
SQLAlchemy persistence, safe benchmark ingestion, background worker architecture,
seed-matched analytics and software-engineering practices. It is **not** a
production-hosted multi-user service. The included benchmark data is entirely
synthetic and must never be presented as real model-performance evidence.

## Acceptance criteria

- [x] Experiments, uploads, benchmark analytics and version comparisons work.
- [x] Deterministic demo generator produces 96 navigation and 48 arena runs.
- [x] Ingestion is idempotent for identical dataset bytes.
- [x] Optional single-admin login, signed sessions, CSRF and bearer API work in tests.
- [x] Versioned OpenAPI JSON and browser API documentation exist.
- [x] SQLite quick start works without Postgres, Redis or Docker locally.
- [x] Alembic migrations and PostgreSQL/Redis integration have CI coverage.
- [x] Leased worker recovery and multi-upload concurrency have test coverage.
- [x] Local Windows test and watchdog exercise were confirmed for v0.8.0.
- [ ] Verify the **v1.0.0** build on Windows after updating the repository.
- [ ] Capture and review portfolio screenshots from the actual running app.
- [ ] Decide repository visibility and license only after a separate privacy review.

The checkboxes reflect evidence available during source review and prior test
runs; new Windows visual review and publish decisions remain deliberately open.

## Pre-release audit

Run from an activated virtual environment in the repository root:

```powershell
py -m pip install -e ".[dev]"
py -m pytest -q --basetemp="$env:LOCALAPPDATA\pytest-replayscope"
py scripts/release_audit.py
py -m flask --app replayscope:create_app seed-demo --dry-run
py -m flask --app replayscope:create_app run --debug
```

The source audit checks for basic secret patterns and accidental tracked
runtime files, required release documents, and consistency between package and
OpenAPI versions. It is **not a complete secret scanner** and does not review
all past Git history. Review the Git commit history before making a repository
public, even when HEAD passes.

## Portfolio materials

Recommended screenshots (from your own localhost browser):

1. **Overview:** two visibly labeled SYNTHETIC DEMO experiments and overall run counts.
2. **Experiment:** Navigator version results filtered to `maze-hard`.
3. **Paired comparison:** Navigator baseline versus candidate with 48 matched pairs.
4. **API reference:** readable endpoints and packaged OpenAPI link.

Record a short walkthrough if desired. Do not include browser credentials,
sensitive local data, screen overlays or developer-debugger information.
Screenshots are intentionally not fabricated or committed by this release.

## Deployment boundary

Keep running on `127.0.0.1` under Flask debug for **local development only**.
Do not share a Flask development server, Docker Compose example with development
credentials, or the unauthenticated default app on the public Internet.
See [deployment-readiness.md](deployment-readiness.md) for the prerequisites of
a real hosted demonstration.

## Known limitations

- Authentication is optional and single-operator; no per-user authorization.
- Local Compose uses demonstrative credentials and cannot be reused in production.
- SQLite + inline workers are optimized for portfolio use, not scale.
- No public hosting, live AI agent, or inference service is included.
- Paired differences are descriptive, not evidence of statistically significant
  performance changes.
- Worker recovery lacks production alerting and a transactional queue outbox.
- License, repository visibility, and public screenshots remain user decisions.

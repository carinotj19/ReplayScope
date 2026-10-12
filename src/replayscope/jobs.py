"""Worker entrypoint shared by inline testing and Redis/RQ.

Upload claiming is an atomic database UPDATE: repeated queue deliveries cannot
process one upload concurrently. The dataset and its normalized rows commit in
one transaction, so a retry does not preserve partially written benchmark runs.
"""
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .ingestion import DatasetError, parse_dataset
from .models import AgentVersion, BenchmarkRun, ReplayUpload, db


def _agent_version_id(name, version):
    """Register an agent version using a database-safe uniqueness upsert."""
    dialect = db.session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        # A portable fallback for other supported SQLAlchemy dialects.
        # The savepoint protects the outer upload transaction from an
        # IntegrityError when two workers insert the same agent concurrently.
        try:
            with db.session.begin_nested():
                entry = AgentVersion(name=name, version=version)
                db.session.add(entry)
                db.session.flush()
                return entry.id
        except IntegrityError:
            pass
        return db.session.scalar(select(AgentVersion.id).filter_by(name=name, version=version))

    statement = insert(AgentVersion).values(name=name, version=version)
    db.session.execute(statement.on_conflict_do_nothing(index_elements=["name", "version"]))
    result = db.session.scalar(select(AgentVersion.id).where(
        AgentVersion.name == name, AgentVersion.version == version
    ))
    if result is None:
        raise RuntimeError("Agent version registration failed")
    return result


def process_upload(upload_id, app=None):
    """Process an upload once; safely acknowledge repeated job delivery.

    Only queued/failed rows may be claimed. A row currently being processed
    is not retried concurrently. Unexpected exceptions are still propagated
    so RQ can apply its configured retry/backoff policy.
    """
    if app is None:
        from . import create_app
        app = create_app()
    with app.app_context():
        result = db.session.execute(
            update(ReplayUpload)
            .where(
                ReplayUpload.id == upload_id,
                ReplayUpload.status.in_(("queued", "failed")),
            )
            .values(status="processing", error=None)
        )
        db.session.commit()
        if result.rowcount != 1:
            db.session.expire_all()
            upload = db.session.get(ReplayUpload, upload_id)
            if upload is None:
                raise ValueError("Unknown upload")
            return upload.status

        upload = db.session.get(ReplayUpload, upload_id)
        try:
            records = parse_dataset(Path(upload.path).read_bytes(), upload.format)
            # A retry replaces ALL of this upload's rows inside the same
            # transaction; no half-written result can become visible.
            db.session.query(BenchmarkRun).filter_by(upload_id=upload.id).delete()
            versions = {}
            for record in records:
                key = (record.agent, record.version)
                if key not in versions:
                    versions[key] = _agent_version_id(*key)
                db.session.add(BenchmarkRun(
                    upload_id=upload.id,
                    agent_version_id=versions[key],
                    scenario=record.scenario,
                    seed=record.seed,
                    outcome=record.outcome,
                    score=record.score,
                    duration_ms=record.duration_ms,
                    failure_reason=record.failure_reason,
                    extra=record.metadata,
                    events=record.events,
                ))
            upload.status = "ready"
            upload.run_count = len(records)
            db.session.commit()
            return "ready"
        except (DatasetError, OSError, ValueError, TypeError) as exc:
            db.session.rollback()
            upload = db.session.get(ReplayUpload, upload_id)
            upload.status = "failed"
            upload.error = str(exc)[:500]
            db.session.commit()
            return "failed"
        except Exception:
            db.session.rollback()
            upload = db.session.get(ReplayUpload, upload_id)
            upload.status = "failed"
            upload.error = "Unexpected processing error"
            db.session.commit()
            raise

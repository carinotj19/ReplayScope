"""Fenced, heartbeat-protected upload processing.

Conditional claims and short transactions guard the upload state. A
monotonically replaced lease token prevents a reclaimed old worker from
committing new benchmark rows or overwriting a newer job's status.
"""
from datetime import timedelta, timezone
from pathlib import Path
from threading import Event, Thread
from uuid import uuid4

from flask import current_app
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .ingestion import DatasetError, parse_dataset
from .models import AgentVersion, BenchmarkRun, ReplayUpload, UploadLease, db, utcnow


class LeaseLost(Exception):
    """The worker's claim expired or was replaced before finalization."""


def _valid_until(value):
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value > utcnow()


def _agent_version_id(name, version):
    """Register agent/version atomically under SQLite and PostgreSQL."""
    dialect = db.session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
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
    value = db.session.scalar(select(AgentVersion.id).where(
        AgentVersion.name == name, AgentVersion.version == version
    ))
    if value is None:
        raise RuntimeError("Agent version registration failed")
    return value


def _claim(upload_id, token, lease_seconds):
    result = db.session.execute(
        update(ReplayUpload)
        .where(ReplayUpload.id == upload_id, ReplayUpload.status.in_(("queued", "failed")))
        .values(status="processing", error=None)
    )
    if result.rowcount != 1:
        db.session.rollback()
        upload = db.session.get(ReplayUpload, upload_id)
        if upload is None:
            raise ValueError("Unknown upload")
        return upload.status

    now = utcnow()
    lease = db.session.get(UploadLease, upload_id)
    if lease is None:
        lease = UploadLease(upload_id=upload_id, attempts=0)
        db.session.add(lease)
    lease.attempts = (lease.attempts or 0) + 1
    lease.token = token
    lease.heartbeat_at = now
    lease.expires_at = now + timedelta(seconds=lease_seconds)
    db.session.commit()
    return None


def _renew_lease(app, upload_id, token):
    with app.app_context():
        now = utcnow()
        try:
            result = db.session.execute(
                update(UploadLease)
                .where(UploadLease.upload_id == upload_id, UploadLease.token == token)
                .values(
                    heartbeat_at=now,
                    expires_at=now + timedelta(seconds=app.config["UPLOAD_LEASE_SECONDS"]),
                )
            )
            db.session.commit()
            return result.rowcount == 1
        except Exception:
            db.session.rollback()
            app.logger.exception("Upload lease heartbeat failed for %s", upload_id)
            return False
        finally:
            db.session.remove()


def _heartbeat(app, upload_id, token, stop):
    interval = app.config["UPLOAD_HEARTBEAT_SECONDS"]
    while not stop.wait(interval):
        if not _renew_lease(app, upload_id, token):
            return


def _owned_upload(upload_id, token, *, require_fresh=False):
    # Lock upload first, then lease: this is the same order used by the
    # recovery sweeper. SQLite serializes writes, PostgreSQL locks rows.
    upload = db.session.execute(
        select(ReplayUpload).where(ReplayUpload.id == upload_id).with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if upload is None or upload.status != "processing":
        raise LeaseLost()
    lease = db.session.execute(
        select(UploadLease).where(UploadLease.upload_id == upload_id).with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if lease is None or lease.token != token:
        raise LeaseLost()
    if require_fresh and not _valid_until(lease.expires_at):
        raise LeaseLost()
    return upload, lease


def _finish(upload_id, token, records):
    upload, lease = _owned_upload(upload_id, token, require_fresh=True)
    db.session.query(BenchmarkRun).filter_by(upload_id=upload_id).delete(synchronize_session=False)
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
    upload.error = None
    lease.token = None
    lease.expires_at = None
    db.session.commit()


def _mark_failed(upload_id, token, error):
    db.session.rollback()
    try:
        upload, lease = _owned_upload(upload_id, token)
    except LeaseLost:
        db.session.rollback()
        return
    upload.status = "failed"
    upload.error = error[:500]
    lease.token = None
    lease.expires_at = None
    db.session.commit()


def process_upload(upload_id, app=None):
    """Perform idempotent processing with heartbeat and commit-time fencing."""
    if app is None:
        from . import create_app
        app = create_app()
    with app.app_context():
        token = str(uuid4())
        claimed = _claim(upload_id, token, app.config["UPLOAD_LEASE_SECONDS"])
        if claimed is not None:
            return claimed
        # Heartbeats use their own SQLAlchemy session because parsing may be
        # slow; the primary session never holds an open transaction during it.
        stop = Event()
        thread = Thread(
            target=_heartbeat, args=(app, upload_id, token, stop),
            daemon=True, name="replayscope-lease-heartbeat",
        )
        thread.start()
        try:
            upload = db.session.get(ReplayUpload, upload_id)
            path, format_name = upload.path, upload.format
            db.session.rollback()
            records = parse_dataset(Path(path).read_bytes(), format_name)
            _finish(upload_id, token, records)
            return "ready"
        except LeaseLost:
            db.session.rollback()
            # A newer worker owns this upload. Never change its state.
            db.session.expire_all()
            record = db.session.get(ReplayUpload, upload_id)
            return record.status if record else "lost"
        except (DatasetError, OSError, ValueError, TypeError) as exc:
            _mark_failed(upload_id, token, str(exc))
            return "failed"
        except Exception:
            _mark_failed(upload_id, token, "Unexpected processing error")
            raise
        finally:
            stop.set()
            thread.join(timeout=5)
            db.session.remove()

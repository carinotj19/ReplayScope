"""Lease fencing and stale-job recovery without local Redis/PostgreSQL."""
import io
import json
from datetime import timedelta
from pathlib import Path
from threading import Event, Thread
from uuid import uuid4

import pytest
from sqlalchemy import inspect

from replayscope import create_app
from replayscope.jobs import _renew_lease, process_upload
from replayscope.models import BenchmarkRun, ReplayUpload, UploadLease, db, utcnow
from replayscope.recovery import scan_stale_uploads


@pytest.fixture
def app(tmp_path):
    application = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "leases.sqlite3"),
        "UPLOAD_DIR": str(tmp_path / "uploads"),
        "PROCESSING_MODE": "inline",
        "UPLOAD_LEASE_SECONDS": 15,
        "UPLOAD_HEARTBEAT_SECONDS": 1,
    })
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


def _sample():
    return json.dumps({"runs": [{
        "agent": "LeaseBot", "version": "v1", "scenario": "test",
        "outcome": "success", "score": 1,
    }]}).encode()


def _upload(app):
    with app.test_client() as client:
        exp = client.post("/api/v1/experiments", json={"name": "Lease tests"}).json["id"]
        result = client.post("/api/v1/uploads", data={
            "experiment_id": str(exp),
            "file": (io.BytesIO(_sample()), "sample.json"),
        })
        assert result.status_code == 201
        assert result.json["status"] == "ready"
        return result.json["id"]


def _prepare_retry(app, uid):
    with app.app_context():
        upload = db.session.get(ReplayUpload, uid)
        upload.status = "failed"
        db.session.commit()


def test_existing_local_database_keeps_uploads_when_lease_table_is_added(tmp_path):
    from sqlalchemy import create_engine, text
    url = "sqlite:///" + str(tmp_path / "legacy.sqlite3")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE old_user_data (id INTEGER PRIMARY KEY, value TEXT)"))
        conn.execute(text("INSERT INTO old_user_data VALUES (1, 'preserved')"))
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": url,
        "AUTO_CREATE_DB": True,
        "TESTING": True,
    })
    with app.app_context():
        assert inspect(db.engine).has_table("upload_leases")
        with db.engine.connect() as conn:
            assert conn.execute(text("SELECT value FROM old_user_data WHERE id=1")).scalar() == "preserved"


def test_ready_job_has_released_token_and_deduplicated_rows(app):
    uid = _upload(app)
    with app.app_context():
        lease = db.session.get(UploadLease, uid)
        assert lease is not None
        assert lease.attempts == 1
        assert lease.token is None
        assert lease.expires_at is None
        assert process_upload(uid, app) == "ready"
        assert db.session.query(BenchmarkRun).filter_by(upload_id=uid).count() == 1


def test_stale_scan_ignores_valid_and_legacy_unleased_uploads(app):
    uid = _upload(app)
    with app.app_context():
        record = db.session.get(ReplayUpload, uid)
        record.status = "processing"
        # Old manual state (no token) is deliberately not auto-reclaimed.
        db.session.commit()
        assert scan_stale_uploads() == (0, 0)
        lease = db.session.get(UploadLease, uid)
        lease.token = str(uuid4())
        lease.expires_at = utcnow() + timedelta(seconds=120)
        db.session.commit()
        assert scan_stale_uploads() == (0, 0)
        assert db.session.get(ReplayUpload, uid).status == "processing"


def test_expired_state_recovers_once_and_does_not_duplicate_runs(app):
    uid = _upload(app)
    with app.app_context():
        record = db.session.get(ReplayUpload, uid)
        record.status = "processing"
        lease = db.session.get(UploadLease, uid)
        lease.token = str(uuid4())
        lease.expires_at = utcnow() - timedelta(seconds=5)
        db.session.commit()
        assert scan_stale_uploads() == (1, 1)
        assert scan_stale_uploads() == (0, 0)
        assert db.session.get(ReplayUpload, uid).status == "ready"
        assert db.session.query(BenchmarkRun).filter_by(upload_id=uid).count() == 1
        assert db.session.get(UploadLease, uid).token is None
    output = app.test_cli_runner().invoke(args=["sweep-stale"])
    assert output.exit_code == 0, output.output
    assert "Scanned 0 expired" in output.output


def test_renewed_heartbeat_prevents_reclamation(app):
    uid = _upload(app)
    with app.app_context():
        record = db.session.get(ReplayUpload, uid)
        record.status = "processing"
        lease = db.session.get(UploadLease, uid)
        token = str(uuid4())
        lease.token = token
        lease.expires_at = utcnow() - timedelta(seconds=1)
        db.session.commit()
    assert _renew_lease(app, uid, token) is True
    with app.app_context():
        assert scan_stale_uploads() == (0, 0)
        assert db.session.get(ReplayUpload, uid).status == "processing"


def test_stale_worker_cannot_commit_after_reclaim(app, monkeypatch):
    uid = _upload(app)
    _prepare_retry(app, uid)

    import replayscope.jobs as jobs
    parse_original = jobs.parse_dataset
    started, resume = Event(), Event()

    def hold_first_parser(raw, format_name):
        if __import__("threading").current_thread().name == "old-worker":
            started.set()
            assert resume.wait(timeout=15)
        return parse_original(raw, format_name)

    monkeypatch.setattr(jobs, "parse_dataset", hold_first_parser)
    statuses = []
    failures = []

    def old_worker():
        try:
            statuses.append(process_upload(uid, app))
        except Exception as exc:
            failures.append(exc)

    worker = Thread(target=old_worker, name="old-worker")
    worker.start()
    try:
        assert started.wait(timeout=15), "The old worker never reached parsing"
        with app.app_context():
            # Simulate missed heartbeats / a stalled worker without waiting 15s.
            lease = db.session.get(UploadLease, uid)
            assert lease.token is not None
            lease.expires_at = utcnow() - timedelta(seconds=1)
            db.session.commit()
            assert scan_stale_uploads() == (1, 1)
            assert db.session.get(ReplayUpload, uid).status == "ready"
        resume.set()
        worker.join(timeout=15)
        assert not worker.is_alive()
        assert not failures
        assert statuses == ["ready"]
        with app.app_context():
            assert db.session.query(BenchmarkRun).filter_by(upload_id=uid).count() == 1
            assert db.session.get(UploadLease, uid).attempts == 3
    finally:
        resume.set()
        worker.join(timeout=15)


def test_explicit_manual_override_revokes_old_token(app):
    uid = _upload(app)
    with app.app_context():
        item = db.session.get(ReplayUpload, uid)
        item.status = "processing"
        lease = db.session.get(UploadLease, uid)
        lease.token = str(uuid4())
        lease.expires_at = utcnow() + timedelta(seconds=1000)
        db.session.commit()
    command = app.test_cli_runner().invoke(args=["recover-upload", uid, "--force-stuck"])
    assert command.exit_code == 0, command.output
    with app.app_context():
        assert db.session.get(ReplayUpload, uid).status == "ready"
        assert db.session.get(UploadLease, uid).token is None
        assert db.session.query(BenchmarkRun).filter_by(upload_id=uid).count() == 1


def test_lease_config_validation(tmp_path):
    config = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "bad.sqlite3"),
    }
    with pytest.raises(ValueError, match="UPLOAD_HEARTBEAT_SECONDS"):
        create_app({**config, "UPLOAD_LEASE_SECONDS": 15, "UPLOAD_HEARTBEAT_SECONDS": 10})

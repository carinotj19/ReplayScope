"""Managed database and queue smoke tests.

Local pytest needs no services: Redis/Postgres tests run when their environment
variables are set (CI or a deliberately configured developer machine).
"""
import io
import json
import os

import pytest
from sqlalchemy import inspect

from replayscope import create_app
from replayscope.models import AgentVersion, BenchmarkRun, ReplayUpload, UploadLease, Experiment, db


def _payload():
    return json.dumps({"runs": [{
        "agent": "IntegrationBot", "version": "1.0", "scenario": "integration",
        "seed": "42", "outcome": "success", "score": 1.0,
    }]}).encode()


def _create_and_upload(client):
    result = client.post("/api/v1/experiments", json={"name": "Integration"})
    assert result.status_code == 201
    experiment_id = result.json["id"]
    response = client.post("/api/v1/uploads", data={
        "experiment_id": str(experiment_id),
        "file": (io.BytesIO(_payload()), "benchmark.json"),
    })
    assert response.status_code == 201
    return experiment_id, response.json


def test_schema_migration_on_fresh_sqlite(tmp_path):
    from flask_migrate import upgrade

    path = tmp_path / "migrated.sqlite3"
    app = create_app({
        "TESTING": True,
        "AUTO_CREATE_DB": False,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(path),
        "UPLOAD_DIR": str(tmp_path / "uploads"),
    })
    with app.app_context():
        assert not inspect(db.engine).has_table("experiments")
        upgrade(directory="migrations")
        tables = set(inspect(db.engine).get_table_names())
        assert {"alembic_version", "experiments", "replay_uploads", "upload_leases",
                "agent_versions", "benchmark_runs"}.issubset(tables)
        # Applying the same migration twice should not duplicate tables.
        upgrade(directory="migrations")
    with app.test_client() as client:
        exp, upload = _create_and_upload(client)
        assert upload["status"] == "ready"
        assert client.get(f"/api/v1/experiments/{exp}/summary").json["versions"][0]["overall"]["runs"] == 1


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="PostgreSQL CI service not configured")
def test_postgresql_migration_and_ingestion(tmp_path):
    from flask_migrate import upgrade

    app = create_app({
        "TESTING": True,
        "AUTO_CREATE_DB": False,
        "SQLALCHEMY_DATABASE_URI": os.environ["TEST_POSTGRES_URL"],
        "UPLOAD_DIR": str(tmp_path / "uploads"),
    })
    with app.app_context():
        upgrade(directory="migrations")
        assert inspect(db.engine).has_table("benchmark_runs")
        assert inspect(db.engine).has_table("upload_leases")
    with app.test_client() as client:
        exp, upload = _create_and_upload(client)
        assert upload["status"] == "ready"
        assert client.get(f"/api/v1/experiments/{exp}/summary").json["versions"][0]["overall"]["task_success_rate"] == 1.0
        # A second experiment reusing the exact same version must not
        # register a duplicate agent/version row in PostgreSQL.
        other = client.post("/api/v1/experiments", json={"name": "Integration second"}).json["id"]
        response = client.post("/api/v1/uploads", data={
            "experiment_id": str(other),
            "file": (io.BytesIO(_payload()), "benchmark.json"),
        })
        assert response.status_code == 201
        assert response.json["status"] == "ready"
        with app.app_context():
            assert db.session.query(AgentVersion).filter_by(
                name="IntegrationBot", version="1.0"
            ).count() == 1


@pytest.mark.skipif(not os.getenv("RUN_REDIS_TESTS"), reason="Redis CI service not configured")
def test_rq_worker_processes_queued_upload(tmp_path, monkeypatch):
    from redis import Redis
    from rq import Queue, SimpleWorker

    redis_url = os.getenv("TEST_REDIS_URL", "redis://127.0.0.1:6379/15")
    db_uri = "sqlite:///" + str(tmp_path / "worker.sqlite3")
    monkeypatch.setenv("DATABASE_URL", db_uri)
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("PROCESSING_MODE", "rq")
    monkeypatch.setenv("AUTO_CREATE_DB", "1")
    monkeypatch.setenv("REDIS_URL", redis_url)

    redis_connection = Redis.from_url(redis_url)
    redis_connection.ping()
    queue = Queue("replayscope", connection=redis_connection)

    app = create_app({"TESTING": True})
    with app.test_client() as client:
        experiment_id, upload = _create_and_upload(client)
        assert upload["status"] == "queued"

    worker = SimpleWorker([queue], connection=redis_connection)
    assert worker.work(burst=True, max_jobs=1)

    with app.app_context():
        record = db.session.get(ReplayUpload, upload["id"])
        db.session.refresh(record)
        assert record.status == "ready"
        assert record.run_count == 1
        assert db.session.query(BenchmarkRun).filter_by(upload_id=record.id).count() == 1

    with app.test_client() as client:
        summary = client.get(f"/api/v1/experiments/{experiment_id}/summary")
        assert summary.status_code == 200
        assert summary.json["versions"][0]["overall"]["task_success_rate"] == 1.0


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="PostgreSQL CI service not configured")
def test_postgres_concurrent_upload_claims_and_agent_registration(tmp_path):
    """Real PostgreSQL transactions with concurrent independent Flask sessions."""
    from concurrent.futures import ThreadPoolExecutor
    from uuid import uuid4
    from pathlib import Path
    from flask_migrate import upgrade
    from replayscope.jobs import process_upload

    app = create_app({
        "TESTING": True,
        "AUTO_CREATE_DB": False,
        "SQLALCHEMY_DATABASE_URI": os.environ["TEST_POSTGRES_URL"],
        "UPLOAD_DIR": str(tmp_path / "stress"),
    })
    with app.app_context():
        upgrade(directory="migrations")
        experiment = Experiment(
            name=f"Concurrency stress {uuid4()}", description="Postgres worker stress test"
        )
        db.session.add(experiment)
        db.session.flush()
        source = Path(tmp_path) / "stress.json"
        source.write_bytes(json.dumps({"runs": [{
            "agent": f"ConcurrentBot-{uuid4()}", "version": "1",
            "scenario": "concurrent", "seed": "7",
            "outcome": "success", "score": 1.0,
        }]}).encode())
        # Make each queued upload unique while sharing one agent/version.
        # This tests the ON CONFLICT registration under real PG contention.
        shared = json.loads(source.read_text())
        shared["runs"][0]["agent"] = f"PGRace-{uuid4()}"
        source.write_bytes(json.dumps(shared).encode())
        agent_name = shared["runs"][0]["agent"]
        uploads = []
        for i in range(12):
            entry = ReplayUpload(
                experiment_id=experiment.id, sha256=f"{i:064x}",
                format="json", filename=f"concurrent-{i}.json",
                path=str(source), status="queued",
            )
            db.session.add(entry)
            db.session.flush()
            uploads.append(entry.id)
        db.session.commit()

    # One independent SQLAlchemy app/session per worker.
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda uid: process_upload(uid, app), uploads))
    assert results == ["ready"] * len(uploads)

    # Duplicate job delivery for a single upload must not add extra rows.
    with ThreadPoolExecutor(max_workers=6) as pool:
        repeated = list(pool.map(lambda _: process_upload(uploads[0], app), range(6)))
    assert repeated == ["ready"] * 6

    with app.app_context():
        assert db.session.query(AgentVersion).filter_by(name=agent_name, version="1").count() == 1
        for uid in uploads:
            record = db.session.get(ReplayUpload, uid)
            assert record.status == "ready"
            assert db.session.query(BenchmarkRun).filter_by(upload_id=uid).count() == 1
            assert db.session.get(UploadLease, uid).token is None

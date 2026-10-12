"""Adversarial input and deterministic worker recovery regression tests."""
import io
import json
from pathlib import Path

import pytest

from replayscope import create_app
from replayscope.ingestion import DatasetError, parse_dataset
from replayscope.jobs import process_upload
from replayscope.models import AgentVersion, BenchmarkRun, ReplayUpload, db


@pytest.fixture()
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "reliability.sqlite3"),
        "UPLOAD_DIR": str(tmp_path / "uploads"),
        "PROCESSING_MODE": "inline",
    })
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def sample(agent="ReliableBot"):
    return {
        "agent": agent, "version": "v1", "scenario": "recovery",
        "outcome": "success", "score": 1,
        "metadata": {"source": "test"},
        "events": [{"type": "checkpoint", "step": 1}],
    }


def make_upload(app, runs=None):
    raw = json.dumps({"runs": runs or [sample()]}).encode()
    with app.test_client() as client:
        response = client.post("/api/v1/experiments", json={"name": "Recovery tests"})
        exp_id = response.json["id"]
        response = client.post("/api/v1/uploads", data={
            "experiment_id": str(exp_id),
            "file": (io.BytesIO(raw), "test.json"),
        })
        assert response.status_code == 201
        return response.json["id"]


@pytest.mark.parametrize("payload", [
    {"metadata": {"blob": "a" * 2049}},
    {"metadata": {("x" * 129): "value"}},
    {"metadata": {"nested": {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": {"j": 1}}}}}}}}}}}},
    {"metadata": {"items": list(range(6001))}},
    {"events": [{"type": "x" * 121}]},
])
def test_rejects_unsafe_nested_payloads(payload):
    entry = sample()
    entry.update(payload)
    with pytest.raises(DatasetError):
        parse_dataset(json.dumps({"runs": [entry]}).encode(), "json")


def test_rejects_duplicate_csv_headers():
    with pytest.raises(DatasetError, match="duplicate column"):
        parse_dataset(b"agent,version,scenario,outcome,score,score\nBot,v1,maze,success,1,99\n", "csv")


def test_accepts_normal_trace_payload():
    parsed = parse_dataset(json.dumps({"runs": [sample()]}).encode(), "json")
    assert parsed[0].events == [{"type": "checkpoint", "step": 1}]


def test_repeated_delivery_and_failed_retry_are_idempotent(app):
    upload_id = make_upload(app)
    with app.app_context():
        assert process_upload(upload_id, app) == "ready"
        assert db.session.query(BenchmarkRun).filter_by(upload_id=upload_id).count() == 1
        record = db.session.get(ReplayUpload, upload_id)
        record.status = "failed"
        db.session.commit()
        assert process_upload(upload_id, app) == "ready"
        assert db.session.query(BenchmarkRun).filter_by(upload_id=upload_id).count() == 1
        assert db.session.query(AgentVersion).filter_by(name="ReliableBot", version="v1").count() == 1


def test_in_progress_job_cannot_be_claimed_again(app):
    upload_id = make_upload(app)
    with app.app_context():
        upload = db.session.get(ReplayUpload, upload_id)
        upload.status = "processing"
        db.session.commit()
        assert process_upload(upload_id, app) == "processing"
        assert db.session.query(BenchmarkRun).filter_by(upload_id=upload_id).count() == 1


def test_unexpected_exception_rolls_back_partial_work(app, monkeypatch):
    upload_id = make_upload(app)
    import replayscope.jobs as jobs

    with app.app_context():
        record = db.session.get(ReplayUpload, upload_id)
        record.status = "failed"
        db.session.commit()
        original = jobs._agent_version_id

        def fail_once(name, version):
            raise RuntimeError("injected transient DB failure")

        monkeypatch.setattr(jobs, "_agent_version_id", fail_once)
        with pytest.raises(RuntimeError, match="injected"):
            process_upload(upload_id, app)
        db.session.expire_all()
        assert db.session.get(ReplayUpload, upload_id).status == "failed"
        assert db.session.get(ReplayUpload, upload_id).error == "Unexpected processing error"
        assert db.session.query(BenchmarkRun).filter_by(upload_id=upload_id).count() == 1
        # Previously ready content remains committed; rollback restored it.
        monkeypatch.setattr(jobs, "_agent_version_id", original)
        assert process_upload(upload_id, app) == "ready"
        assert db.session.query(BenchmarkRun).filter_by(upload_id=upload_id).count() == 1


def test_recovery_cli_requires_explicit_override_for_stuck_worker(app):
    uid = make_upload(app)
    with app.app_context():
        db.session.get(ReplayUpload, uid).status = "processing"
        db.session.commit()
    runner = app.test_cli_runner()
    blocked = runner.invoke(args=["recover-upload", uid])
    assert blocked.exit_code != 0
    assert "STOPPED" in blocked.output
    with app.app_context():
        assert db.session.get(ReplayUpload, uid).status == "processing"
    restored = runner.invoke(args=["recover-upload", uid, "--force-stuck"])
    assert restored.exit_code == 0, restored.output
    assert "recovered successfully" in restored.output
    with app.app_context():
        upload = db.session.get(ReplayUpload, uid)
        assert upload.status == "ready"
        assert db.session.query(BenchmarkRun).filter_by(upload_id=uid).count() == 1


def test_recovery_failed_source_returns_cli_error(app):
    uid = make_upload(app)
    with app.app_context():
        upload = db.session.get(ReplayUpload, uid)
        Path(upload.path).write_bytes(b"broken json")
        upload.status = "failed"
        db.session.commit()
    result = app.test_cli_runner().invoke(args=["recover-upload", uid])
    assert result.exit_code != 0
    assert "failed" in result.output.lower()
    with app.app_context():
        assert db.session.get(ReplayUpload, uid).status == "failed"


def test_rejection_occurs_before_any_upload_is_saved(app):
    with app.test_client() as client:
        exp = client.post("/api/v1/experiments", json={"name": "Bad input"}).json["id"]
        raw = json.dumps({"runs": [{**sample(), "metadata": {"huge": "!"*2049}}]}).encode()
        response = client.post("/api/v1/uploads", data={
            "experiment_id": str(exp), "file": (io.BytesIO(raw), "bad.json"),
        })
        assert response.status_code == 422
    with app.app_context():
        assert db.session.query(ReplayUpload).count() == 0

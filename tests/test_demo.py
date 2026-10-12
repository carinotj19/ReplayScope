"""CLI demo data: deterministic, idempotent, and non-destructive."""
import hashlib
from pathlib import Path

import pytest

from replayscope import create_app
from replayscope.comparisons import compare_versions
from replayscope.demo import build_demo_datasets
from replayscope.ingestion import parse_dataset
from replayscope.models import AgentVersion, BenchmarkRun, Experiment, ReplayUpload, db


@pytest.fixture()
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "demo.sqlite3"),
        "UPLOAD_DIR": str(tmp_path / "uploads"),
        "PROCESSING_MODE": "inline",
    })
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def test_sample_generation_is_deterministic_and_valid():
    first = build_demo_datasets()
    assert first == build_demo_datasets()
    assert len(first) == 2
    assert [len(parse_dataset(raw, "json")) for _, _, raw in first] == [96, 48]
    for name, description, raw in first:
        assert "SYNTHETIC DEMO" in name
        assert description
        assert b'"synthetic":true' in raw


def test_cli_dry_run_does_not_insert_rows_or_files(app):
    result = app.test_cli_runner().invoke(args=["seed-demo", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "[dry-run]" in result.output
    with app.app_context():
        assert db.session.query(Experiment).count() == 0
        assert db.session.query(ReplayUpload).count() == 0
    assert not Path(app.config["UPLOAD_DIR"]).exists()


def test_cli_seed_is_idempotent_and_preserves_user_data(app):
    with app.app_context():
        db.session.add(Experiment(name="My personal experiment", description="Keep me"))
        db.session.commit()

    cli = app.test_cli_runner()
    initial = cli.invoke(args=["seed-demo"])
    assert initial.exit_code == 0, initial.output
    assert initial.output.count("[created]") == 2

    with app.app_context():
        assert db.session.query(Experiment).count() == 3
        assert db.session.query(ReplayUpload).count() == 2
        assert db.session.query(BenchmarkRun).count() == 144
        counts = sorted(row.run_count for row in db.session.query(ReplayUpload).all())
        assert counts == [48, 96]
        assert db.session.query(Experiment).filter_by(name="My personal experiment").one().description == "Keep me"
        experiments = db.session.query(Experiment).filter(Experiment.name.like("SYNTHETIC DEMO%")).all()
        for exp in experiments:
            assert db.session.query(ReplayUpload).filter_by(experiment_id=exp.id).one().status == "ready"
        upload_paths = [Path(u.path) for u in db.session.query(ReplayUpload).all()]
        digests = [u.sha256 for u in db.session.query(ReplayUpload).all()]
        for path, digest in zip(upload_paths, digests):
            assert path.exists()
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest

    again = cli.invoke(args=["seed-demo"])
    assert again.exit_code == 0, again.output
    assert again.output.count("[reused]") == 2
    with app.app_context():
        assert db.session.query(Experiment).count() == 3
        assert db.session.query(ReplayUpload).count() == 2
        assert db.session.query(BenchmarkRun).count() == 144


def test_demo_is_browsable_and_pairable(app):
    result = app.test_cli_runner().invoke(args=["seed-demo"])
    assert result.exit_code == 0, result.output
    with app.app_context():
        exp = db.session.query(Experiment).filter_by(
            name="SYNTHETIC DEMO — Navigation Trials"
        ).one()
        versions = db.session.query(AgentVersion).filter_by(name="Navigator").all()
        assert len(versions) == 2
        ids = {item.version: item.id for item in versions}
        compare = compare_versions(exp.id, ids["baseline"], ids["candidate"])
        assert compare["overall"]["pairs"] == 48
        assert compare["excluded"]["ambiguous_overlap_keys"] == 0
        assert compare["overall"]["mean_score_delta"] is not None
        exp_id = exp.id
    with app.test_client() as client:
        assert b"SYNTHETIC DEMO" in client.get("/").data
        assert client.get(f"/experiments/{exp_id}").status_code == 200
        assert client.get(f"/experiments/{exp_id}/compare").status_code == 200

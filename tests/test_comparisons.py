"""Functional and API coverage for deterministic paired comparisons."""
import io
import json

import pytest

from replayscope import create_app
from replayscope.comparisons import compare_runs
from replayscope.models import db


def record(version, scenario, seed, score, duration=None):
    return {
        "agent_version_id": version, "scenario": scenario,
        "seed": seed, "score": score, "outcome": "win",
        "duration_ms": duration,
    }


def test_exact_seed_scenario_matching_and_exclusions():
    rows = [
        record(1, "maze", "1", 10, 100),
        record(2, "maze", "1", 13, 90),
        record(1, "maze", "2", 5, 200),
        record(2, "maze", "2", 3, 190),
        record(1, "maze", None, 9),
        record(2, "other", "1", 9),
        record(1, "maze", "duplicate", 20),
        record(1, "maze", "duplicate", 21),
        record(2, "maze", "duplicate", 19),
    ]
    result = compare_runs(rows, 1, 2)
    assert result["overall"]["pairs"] == 2
    assert result["overall"]["mean_score_delta"] == 0.5
    assert result["overall"]["median_score_delta"] == 0.5
    assert result["overall"]["higher_score"] == 1
    assert result["overall"]["lower_score"] == 1
    assert result["overall"]["mean_duration_delta_ms"] == -10
    assert result["excluded"] == {
        "baseline_unseeded": 1,
        "candidate_unseeded": 0,
        "baseline_only_keys": 0,
        "candidate_only_keys": 1,
        "ambiguous_overlap_keys": 1,
    }
    assert result["by_scenario"]["maze"]["pairs"] == 2


def test_no_overlap_is_not_a_fake_pair():
    result = compare_runs([record(1, "a", "1", 1), record(2, "a", "2", 2)], 1, 2)
    assert result["overall"]["pairs"] == 0
    assert result["overall"]["mean_score_delta"] is None
    assert result["pair_sample"] == []


@pytest.fixture()
def client(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "compare.sqlite3"),
        "UPLOAD_DIR": str(tmp_path / "uploads"),
        "PROCESSING_MODE": "inline",
    })
    with app.test_client() as test_client:
        yield test_client
    with app.app_context():
        db.session.remove()
        db.drop_all()


def setup_comparison(client):
    exp = client.post("/api/v1/experiments", json={"name": "Matching test"}).json["id"]
    runs = [
        {"agent": "Pathfinder", "version": "1.0", "scenario": "maze", "seed": 7,
         "outcome": "loss", "score": 10},
        {"agent": "Pathfinder", "version": "1.1", "scenario": "maze", "seed": 7,
         "outcome": "win", "score": 18},
        {"agent": "Pathfinder", "version": "1.0", "scenario": "other", "seed": 8,
         "outcome": "win", "score": 20},
        {"agent": "Pathfinder", "version": "1.1", "scenario": "other", "seed": 8,
         "outcome": "win", "score": 23},
        {"agent": "Another", "version": "base", "scenario": "maze", "seed": 7,
         "outcome": "success", "score": 50},
    ]
    response = client.post("/api/v1/uploads", data={
        "experiment_id": str(exp),
        "file": (io.BytesIO(json.dumps({"runs": runs}).encode()), "results.json"),
    })
    assert response.status_code == 201
    return exp


def test_comparison_api_and_html(client):
    exp = setup_comparison(client)
    versions = client.get("/api/v1/agent-versions").json
    base = next(v["id"] for v in versions if v["name"] == "Pathfinder" and v["version"] == "1.0")
    candidate = next(v["id"] for v in versions if v["name"] == "Pathfinder" and v["version"] == "1.1")

    response = client.get(
        f"/api/v1/experiments/{exp}/compare?baseline_id={base}&candidate_id={candidate}"
    )
    assert response.status_code == 200
    assert response.json["overall"]["pairs"] == 2
    assert response.json["overall"]["mean_score_delta"] == 5.5
    assert response.json["by_scenario"]["maze"]["mean_score_delta"] == 8
    assert response.json["by_scenario"]["other"]["mean_score_delta"] == 3

    filtered = client.get(
        f"/api/v1/experiments/{exp}/compare?baseline_id={base}&candidate_id={candidate}&scenario=maze"
    )
    assert filtered.json["overall"]["pairs"] == 1

    page = client.get(f"/experiments/{exp}/compare")
    assert page.status_code == 200
    assert b"Paired comparison" in page.data
    assert b"Matched run sample" in page.data
    assert b"5.50" in page.data
    assert b"Excluded observations" in page.data
    assert b"Same" not in page.data
    assert b"Paired comparison" in client.get(f"/experiments/{exp}").data


def test_validation_scoping(client):
    exp = setup_comparison(client)
    versions = client.get("/api/v1/agent-versions").json
    one, two = next(v["id"] for v in versions if v["name"] == "Pathfinder" and v["version"] == "1.0"), next(v["id"] for v in versions if v["name"] == "Pathfinder" and v["version"] == "1.1")
    other = next(v["id"] for v in versions if v["name"] == "Another")

    assert client.get(f"/api/v1/experiments/{exp}/compare").status_code == 400
    assert client.get(f"/api/v1/experiments/{exp}/compare?baseline_id={one}&candidate_id={one}").status_code == 400
    assert client.get(f"/api/v1/experiments/{exp}/compare?baseline_id={one}&candidate_id={other}").status_code == 400
    assert client.get(f"/api/v1/experiments/999/compare?baseline_id={one}&candidate_id={two}").status_code == 404
    assert client.get(f"/experiments/{exp}/compare?baseline_id={one}&candidate_id={other}").status_code == 200
    assert b"Compare versions of the same agent" in client.get(f"/experiments/{exp}/compare?baseline_id={one}&candidate_id={other}").data

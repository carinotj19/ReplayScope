import io
import json

import pytest

from replayscope import create_app
from replayscope.models import db


@pytest.fixture
def client(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "test.db"),
        "UPLOAD_DIR": str(tmp_path / "uploads"),
        "PROCESSING_MODE": "inline",
    })
    with app.test_client() as client:
        yield client
    with app.app_context():
        db.session.remove()
        db.drop_all()


def new_experiment(client, name="Benchmark"):
    response = client.post("/api/v1/experiments", json={"name": name})
    assert response.status_code == 201
    return response.json["id"]


def data_bytes():
    return json.dumps({"runs": [
        {"agent": "Navigator", "version": "v1", "scenario": "maze",
         "seed": 10, "outcome": "win", "score": 90, "duration_ms": 200,
         "events": [{"type": "move", "position": [1, 2]}]},
        {"agent": "Navigator", "version": "v2", "scenario": "maze",
         "seed": 10, "outcome": "loss", "score": 20, "failure_reason": "collision"},
        {"agent": "Navigator", "version": "v2", "scenario": "search",
         "seed": 11, "outcome": "success", "score": 30},
    ]}).encode()


def post_upload(client, experiment_id, raw=None, filename="sample.json"):
    if raw is None:
        raw = data_bytes()
    return client.post("/api/v1/uploads", data={
        "experiment_id": str(experiment_id),
        "file": (io.BytesIO(raw), filename),
    })


def test_workflow(client):
    assert client.get("/health").json["status"] == "ok"
    exp = new_experiment(client)
    response = post_upload(client, exp)
    assert response.status_code == 201
    assert response.json["status"] == "ready"
    assert response.json["run_count"] == 3
    uid = response.json["id"]
    assert client.get(f"/api/v1/uploads/{uid}").json["status"] == "ready"
    assert len(client.get("/api/v1/agent-versions").json) == 2

    summary = client.get(f"/api/v1/experiments/{exp}/summary").json
    assert len(summary["versions"]) == 2
    first, second = summary["versions"]
    assert first["overall"]["game_win_rate"] == 1.0
    assert second["overall"]["game_win_rate"] == 0.0
    assert second["overall"]["task_success_rate"] == 1.0
    assert second["overall"]["failure_reasons"] == {"collision": 1}

    page = client.get(f"/api/v1/experiments/{exp}/runs?page=2&per_page=1").json
    assert page["total"] == 3
    assert len(page["items"]) == 1
    scoped = client.get(f"/api/v1/experiments/{exp}/summary?scenario=search").json
    assert len(scoped["versions"]) == 1
    assert scoped["versions"][0]["overall"]["runs"] == 1


def test_validation_and_deduplication(client):
    exp = new_experiment(client)
    assert post_upload(client, exp).status_code == 201
    assert post_upload(client, exp).status_code == 200
    assert client.get(f"/api/v1/experiments/{exp}/runs").json["total"] == 3
    bad = b'{"runs":[{"agent":"A","version":"v1","scenario":"maze","outcome":"loss","score":"NaN"}]}'
    response = post_upload(client, exp, raw=bad)
    assert response.status_code == 422
    assert "finite number" in response.json["error"]
    assert client.post("/api/v1/experiments", json={"name": "Benchmark"}).status_code == 409


def test_csv(client):
    exp = new_experiment(client)
    raw = b"agent,version,scenario,outcome,score\nBot,v1,task,success,100\n"
    response = post_upload(client, exp, raw, "results.csv")
    assert response.status_code == 201
    summary = client.get(f"/api/v1/experiments/{exp}/summary").json
    assert summary["versions"][0]["overall"]["task_success_rate"] == 1.0


def test_pagination_errors(client):
    exp = new_experiment(client)
    assert client.get(f"/api/v1/experiments/{exp}/runs?page=0").status_code == 400


def test_api_returns_json_for_404_and_large_payload(client):
    missing = client.get("/api/v1/not-a-real-endpoint")
    assert missing.status_code == 404
    assert "error" in missing.json

    limit = client.application.config["MAX_CONTENT_LENGTH"]
    client.application.config["MAX_CONTENT_LENGTH"] = 120
    try:
        result = client.post("/api/v1/experiments",
                             data=b"X" * 512,
                             content_type="application/json")
        assert result.status_code == 413
        assert "error" in result.json
    finally:
        client.application.config["MAX_CONTENT_LENGTH"] = limit


def test_api_filters_reject_oversized_scenario(client):
    exp = new_experiment(client)
    scenario = "x" * 121
    assert client.get(
        f"/api/v1/experiments/{exp}/runs?scenario={scenario}"
    ).status_code == 400
    assert client.get(
        f"/api/v1/experiments/{exp}/summary?scenario={scenario}"
    ).status_code == 400

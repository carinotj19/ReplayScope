import io
import json

import pytest

from replayscope import create_app
from replayscope.models import db
from replayscope.orbit import analyze, ReplayError
from replayscope.stats import wilson


def sample():
    obs = {"planets": [[0, 0, 20, 20, 2, 30, 4],
                       [1, 1, 80, 80, 2, 12, 2]],
           "fleets": [[2, 0, 30, 30, 0.1, 0, 5]]}
    return {"steps": [[{"observation": obs}, {"observation": obs}]]}


@pytest.fixture
def client(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "test.db"),
        "UPLOAD_DIR": str(tmp_path / "uploads"),
        "REPLAYSCOPE_JOBS": "inline",
    })
    with app.test_client() as c:
        yield c
    with app.app_context():
        db.session.remove()
        db.drop_all()


def test_orbit_adapter():
    metrics = analyze(sample(), 0)
    assert metrics["outcome"] == "win"
    assert metrics["final_score"] == 35
    assert metrics["mode"] == "2P"
    with pytest.raises(ReplayError):
        analyze(sample(), 3)


def test_statistics():
    assert wilson(0, 0) is None
    low, high = wilson(5, 10)
    assert low < 0.5 < high


def test_api_upload_and_summary(client):
    assert client.get("/health").json["status"] == "ok"
    agent = client.post("/api/agent-versions", json={"name": "MyBot", "version": "v1"})
    experiment = client.post("/api/experiments", json={"name": "Baseline"})
    assert agent.status_code == 201 and experiment.status_code == 201
    data = {
        "experiment_id": str(experiment.json["id"]),
        "agent_version_id": str(agent.json["id"]),
        "player_slot": "0",
        "file": (io.BytesIO(json.dumps(sample()).encode()), "episode.json"),
    }
    response = client.post("/api/replays", data=data)
    assert response.status_code == 201
    assert response.json["status"] == "ready"
    replay_id = response.json["id"]
    assert client.get(f"/api/replays/{replay_id}").json["metrics"]["final_score"] == 35
    summary = client.get(f"/api/experiments/{experiment.json['id']}/summary").json
    assert summary["versions"][0]["overall"]["games"] == 1
    assert summary["versions"][0]["by_mode"]["2P"]["win_rate"] == 1.0


def test_bad_upload(client):
    agent = client.post("/api/agent-versions", json={"name": "Test", "version": "v1"})
    exp = client.post("/api/experiments", json={"name": "Bad JSON"})
    response = client.post("/api/replays", data={
        "experiment_id": str(exp.json["id"]),
        "agent_version_id": str(agent.json["id"]),
        "player_slot": "0",
        "file": (io.BytesIO(b"not valid json"), "bad.json"),
    })
    assert response.status_code == 400

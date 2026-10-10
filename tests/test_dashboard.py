"""Browser-level smoke tests using Flask's HTML test client."""
import io
import json

import pytest

from replayscope import create_app
from replayscope.models import db


@pytest.fixture()
def client(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "web.sqlite3"),
        "UPLOAD_DIR": str(tmp_path / "uploads"),
        "PROCESSING_MODE": "inline",
    })
    with app.test_client() as c:
        yield c
    with app.app_context():
        db.session.remove()
        db.drop_all()


def new_experiment(client, name="Portfolio demo"):
    resp = client.post("/api/v1/experiments", json={
        "name": name,
        "description": "A small reproducible experiment",
    })
    assert resp.status_code == 201
    return resp.json["id"]


def upload(client, eid, runs):
    data = {"runs": runs}
    return client.post("/api/v1/uploads", data={
        "experiment_id": str(eid),
        "file": (io.BytesIO(json.dumps(data).encode("utf-8")), "demo.json"),
    })


def runs():
    return [
        {"agent": "Pathfinder", "version": "1.0", "scenario": "maze",
         "seed": 10, "outcome": "loss", "score": 35,
         "failure_reason": "timeout", "events": [{"type": "stalled", "turn": 3}]},
        {"agent": "Pathfinder", "version": "1.1", "scenario": "maze",
         "seed": 10, "outcome": "win", "score": 92},
        {"agent": "Labeler", "version": "baseline", "scenario": "classification",
         "outcome": "success", "score": 1},
    ]


def test_home_empty_and_assets(client):
    page = client.get("/")
    assert page.status_code == 200
    assert b"Benchmark intelligence" in page.data
    assert b"No experiments yet" in page.data
    assert b'data-create-experiment' in page.data
    assert client.get("/static/dashboard.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200


def test_dashboard_after_upload(client):
    eid = new_experiment(client)
    response = upload(client, eid, runs())
    assert response.status_code == 201
    assert response.json["status"] == "ready"

    home = client.get("/")
    assert b"Portfolio demo" in home.data
    assert b"3 runs" in home.data

    page = client.get(f"/experiments/{eid}")
    assert page.status_code == 200
    assert b"Version comparison" in page.data
    assert b"Pathfinder" in page.data
    assert b"Labeler" in page.data
    assert b"Run history" in page.data
    assert b"timeout" in page.data
    assert b"stalled" in page.data
    assert b"data-upload-form" in page.data
    assert b"100%" in page.data


def test_scenario_filter_and_nonexistent_experiment(client):
    eid = new_experiment(client)
    assert upload(client, eid, runs()).status_code == 201
    page = client.get(f"/experiments/{eid}?scenario=maze")
    assert page.status_code == 200
    assert b"Pathfinder" in page.data
    assert b"Labeler" not in page.data
    other = client.get(f"/experiments/{eid}?scenario=missing")
    assert b"No results in this scope" in other.data
    assert client.get("/experiments/989898").status_code == 404
    assert client.get(f"/experiments/{eid}?page=oops").status_code == 400


def test_template_escapes_untrusted_labels(client):
    eid = new_experiment(client, "<script>alert(1)</script>")
    page = client.get("/")
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in page.data
    assert b"<script>alert(1)</script>" not in page.data
    assert client.get(f"/experiments/{eid}").status_code == 200


def test_history_pagination(client):
    eid = new_experiment(client)
    many = [
        {"agent": "Tester", "version": "v1", "scenario": "test",
         "outcome": "success", "score": i, "seed": i}
        for i in range(23)
    ]
    assert upload(client, eid, many).status_code == 201
    page = client.get(f"/experiments/{eid}?page=2")
    assert page.status_code == 200
    assert b"Page 2 of 2" in page.data
    assert b"23 RUNS" in page.data

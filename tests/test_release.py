"""Release acceptance: real app factory + seed CLI + web/API paths."""
from importlib.metadata import version as distribution_version
import json

from replayscope import create_app
from replayscope.models import BenchmarkRun, Experiment, db


def test_fresh_portfolio_demo_end_to_end(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "release.db"),
        "UPLOAD_DIR": str(tmp_path / "uploads"),
        "PROCESSING_MODE": "inline",
        "AUTH_ENABLED": False,
    })
    assert app.config["APP_VERSION"] == distribution_version("replayscope")

    preview = app.test_cli_runner().invoke(args=["seed-demo", "--dry-run"])
    assert preview.exit_code == 0
    assert preview.output.count("[dry-run]") == 2

    first = app.test_cli_runner().invoke(args=["seed-demo"])
    assert first.exit_code == 0, first.output
    assert first.output.count("[created]") == 2
    again = app.test_cli_runner().invoke(args=["seed-demo"])
    assert again.exit_code == 0, again.output
    assert again.output.count("[reused]") == 2

    with app.app_context():
        experiments = db.session.query(Experiment).all()
        assert len(experiments) == 2
        assert db.session.query(BenchmarkRun).count() == 144
        navigation = next(x for x in experiments if "Navigation" in x.name)
        navigation_id = navigation.id

    with app.test_client() as client:
        assert client.get("/health").json == {"service": "replayscope", "status": "ok"}
        for route in ("/", "/docs", f"/experiments/{navigation_id}",
                      f"/experiments/{navigation_id}/compare", "/static/styles.css",
                      "/static/dashboard.js", "/static/favicon.svg"):
            response = client.get(route)
            assert response.status_code == 200, (route, response.status_code)
        spec = client.get("/api/v1/openapi.json").json
        assert spec["info"]["version"] == app.config["APP_VERSION"]
        versions = client.get("/api/v1/agent-versions").json
        base_id = next(x["id"] for x in versions if x["name"] == "Navigator" and x["version"] == "baseline")
        cand_id = next(x["id"] for x in versions if x["name"] == "Navigator" and x["version"] == "candidate")
        response = client.get(
            f"/api/v1/experiments/{navigation_id}/compare"
            f"?baseline_id={base_id}&candidate_id={cand_id}"
        )
        assert response.status_code == 200
        assert response.json["overall"]["pairs"] == 48
        assert response.json["excluded"]["ambiguous_overlap_keys"] == 0
        assert client.get("/api/v1/experiments/999999/runs").status_code == 404
        assert client.get("/api/v1/experiments/999999/runs").is_json

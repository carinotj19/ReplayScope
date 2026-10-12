"""Contract tests for documentation, packaging, and HTTP behavior."""
from importlib.resources import files
import json
import re

from replayscope import create_app


def test_docs_render_and_spec_is_valid_json(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "docs.db"),
    })
    with app.test_client() as client:
        page = client.get("/docs")
        assert page.status_code == 200
        assert b"REST API reference" in page.data
        assert f"ReplayScope v{app.config['APP_VERSION']}".encode() in page.data
        assert b"Upload benchmark JSON or CSV" in page.data
        spec_response = client.get("/api/v1/openapi.json")
        assert spec_response.status_code == 200
        assert spec_response.json["openapi"] == "3.1.0"
        assert "BearerAuth" in spec_response.json["components"]["securitySchemes"]
        assert client.get("/static/favicon.svg").status_code == 200
        assert client.get("/favicon.ico").status_code == 302

        spec = spec_response.json
        documented = set(spec["paths"])
        actual = set()
        actual_methods = {}
        for rule in app.url_map.iter_rules():
            if rule.rule == "/health" or rule.rule.startswith("/api/v1/"):
                normalized = re.sub(r"<(?:[a-z]+:)?([a-z_]+)>", r"{\1}", rule.rule)
                actual.add(normalized)
                actual_methods.setdefault(normalized, set()).update(
                    set(rule.methods) & {"GET", "POST", "PATCH", "PUT", "DELETE"}
                )
        assert documented == actual
        for path, methods in spec["paths"].items():
            listed = {method.upper() for method in methods}
            assert listed == actual_methods[path]


def test_contract_is_packaged_as_source():
    data = json.loads(
        files("replayscope").joinpath("openapi.json").read_text(encoding="utf-8")
    )
    assert data["info"]["title"] == "ReplayScope API"
    assert data["info"]["version"] == "1.0.0"

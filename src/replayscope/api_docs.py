"""API reference pages and machine-readable OpenAPI schema.

The schema is packaged with the Python distribution, not fetched externally.
"""
from importlib.resources import files
import json

from flask import Blueprint, jsonify, render_template

docs_ui = Blueprint("docs_ui", __name__)


def _spec():
    return json.loads(files("replayscope").joinpath("openapi.json").read_text(encoding="utf-8"))


@docs_ui.get("/api/v1/openapi.json")
def openapi():
    return jsonify(_spec())


@docs_ui.get("/docs")
def docs():
    spec = _spec()
    sections = []
    for path, methods in spec["paths"].items():
        for method, operation in methods.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            sections.append({
                "method": method.upper(),
                "path": path,
                "title": operation.get("summary", path),
                "description": operation.get("description", ""),
                "params": operation.get("parameters", []),
                "responses": operation.get("responses", {}),
            })
    return render_template("docs.html", active_page="docs", sections=sections)

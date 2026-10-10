"""ReplayScope Flask application factory."""
import os
from pathlib import Path

from flask import Flask, jsonify
from flask_migrate import Migrate

from .models import db

migrate = Migrate(compare_type=True)


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    external_db_url = os.getenv("DATABASE_URL")
    database_url = external_db_url or (
        "sqlite:///" + str(Path(app.instance_path) / "replayscope.sqlite3")
    )
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]
    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
        UPLOAD_DIR=os.getenv("UPLOAD_DIR") or str(Path(app.instance_path) / "uploads"),
        PROCESSING_MODE=os.getenv("PROCESSING_MODE", "inline"),
        REDIS_URL=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        # Keep local SQLite quick-start unchanged. Managed databases use migrations.
        AUTO_CREATE_DB=os.getenv("AUTO_CREATE_DB", "0" if external_db_url else "1") == "1",
    )
    if test_config:
        app.config.update(test_config)
    if app.config["PROCESSING_MODE"] not in ("inline", "rq"):
        raise ValueError("PROCESSING_MODE must be inline or rq")

    db.init_app(app)
    migrate.init_app(app, db)
    from .routes import api
    from .web import web
    app.register_blueprint(api, url_prefix="/api/v1")
    app.register_blueprint(web)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "replayscope"})

    if app.config["AUTO_CREATE_DB"]:
        with app.app_context():
            db.create_all()
    return app

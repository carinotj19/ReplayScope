"""ReplayScope Flask application factory."""
import os
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException
from flask_migrate import Migrate

from .models import db
from .security import configure_security
from .api_docs import docs_ui

migrate = Migrate(compare_type=True)


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    external_db_url = os.getenv("DATABASE_URL")
    database_url = external_db_url or (
        "sqlite:///" + str(Path(app.instance_path) / "replayscope.sqlite3")
    )
    try:
        app_version = package_version("replayscope")
    except PackageNotFoundError:
        app_version = "dev"
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]
    app.config.from_mapping(
        APP_VERSION=app_version,
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
        UPLOAD_DIR=os.getenv("UPLOAD_DIR") or str(Path(app.instance_path) / "uploads"),
        PROCESSING_MODE=os.getenv("PROCESSING_MODE", "inline"),
        UPLOAD_LEASE_SECONDS=int(os.getenv("REPLAYSCOPE_LEASE_SECONDS", "120")),
        UPLOAD_HEARTBEAT_SECONDS=int(os.getenv("REPLAYSCOPE_HEARTBEAT_SECONDS", "20")),
        REDIS_URL=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        AUTO_CREATE_DB=os.getenv("AUTO_CREATE_DB", "0" if external_db_url else "1") == "1",
        AUTH_ENABLED=os.getenv("REPLAYSCOPE_AUTH_ENABLED", "0") == "1",
        SECRET_KEY=os.getenv("REPLAYSCOPE_SECRET_KEY"),
        ADMIN_PASSWORD_HASH=os.getenv("REPLAYSCOPE_ADMIN_PASSWORD_HASH"),
        API_TOKEN=os.getenv("REPLAYSCOPE_API_TOKEN"),
        RATELIMIT_STORAGE_URI=os.getenv("REPLAYSCOPE_RATE_STORAGE_URL", "memory://"),
        SESSION_COOKIE_SECURE=os.getenv("REPLAYSCOPE_SECURE_COOKIE", "0") == "1",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config:
        app.config.update(test_config)
    if not (15 <= app.config["UPLOAD_LEASE_SECONDS"] <= 86400):
        raise ValueError("UPLOAD_LEASE_SECONDS must be between 15 and 86400")
    if not (1 <= app.config["UPLOAD_HEARTBEAT_SECONDS"] * 3 < app.config["UPLOAD_LEASE_SECONDS"]):
        raise ValueError("UPLOAD_HEARTBEAT_SECONDS must be at least 1 and below one third of lease duration")
    if app.config["PROCESSING_MODE"] not in ("inline", "rq"):
        raise ValueError("PROCESSING_MODE must be inline or rq")

    configure_security(app)
    db.init_app(app)
    migrate.init_app(app, db)
    from .routes import api
    from .web import web
    app.register_blueprint(api, url_prefix="/api/v1")
    app.register_blueprint(web)
    app.register_blueprint(docs_ui)
    from .demo import register_demo_cli
    register_demo_cli(app)
    from .recovery import register_recovery_cli
    register_recovery_cli(app)

    @app.get("/favicon.ico")
    def favicon():
        from flask import redirect, url_for
        return redirect(url_for("static", filename="favicon.svg"), code=302)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "replayscope"})

    @app.errorhandler(HTTPException)
    def http_error(exc):
        if request.path.startswith("/api/v1/"):
            return jsonify({"error": exc.description}), exc.code
        return exc

    if app.config["AUTO_CREATE_DB"]:
        with app.app_context():
            db.create_all()
    return app

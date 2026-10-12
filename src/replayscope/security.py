"""Single-operator security for a local/portfolio Flask application.

When enabled: session login for the dashboard, optional bearer tokens for
automation, and CSRF checks for every session-authenticated unsafe request.
This is not a multi-user permissions system.
"""
import hmac
import secrets
from datetime import timedelta

from flask import (
    Blueprint, abort, current_app, jsonify, redirect,
    render_template, request, session, url_for,
)
from werkzeug.security import check_password_hash
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

security = Blueprint("security", __name__)
limiter = Limiter(key_func=get_remote_address, default_limits=[])


def csrf_token():
    """Return a session-bound anti-CSRF token for authenticated browser flows."""
    if not current_app.config["AUTH_ENABLED"]:
        return ""
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def _csrf_valid():
    expected = session.get("_csrf")
    supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def _bearer_authorized():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return False
    token = current_app.config.get("API_TOKEN")
    candidate = header[7:]
    return bool(token and candidate and hmac.compare_digest(candidate, token))


def _api_error(message, status):
    return jsonify({"error": message}), status


@security.get("/login")
def login_page():
    if not current_app.config["AUTH_ENABLED"] or session.get("authenticated"):
        return redirect(url_for("web.home"))
    return render_template("login.html", csrf_value=csrf_token(), error=None)


@security.post("/login")
@limiter.limit("5 per minute", exempt_when=lambda: not current_app.config["AUTH_ENABLED"])
def login():
    if not current_app.config["AUTH_ENABLED"]:
        abort(404)
    if not _csrf_valid():
        abort(403)
    password = request.form.get("password", "")
    if check_password_hash(current_app.config["ADMIN_PASSWORD_HASH"], password):
        session.clear()
        session.permanent = True
        session["authenticated"] = True
        csrf_token()
        return redirect(url_for("web.home"), code=303)
    return render_template(
        "login.html",
        csrf_value=csrf_token(),
        error="Incorrect password.",
    ), 401


@security.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("security.login_page"), code=303)


def configure_security(app):
    """Install guards before app blueprints; no secrets or users are stored in DB."""
    if app.config["AUTH_ENABLED"]:
        if not app.config.get("SECRET_KEY") or not app.config.get("ADMIN_PASSWORD_HASH"):
            raise ValueError(
                "AUTH_ENABLED requires SECRET_KEY and ADMIN_PASSWORD_HASH"
            )
        if len(app.config["SECRET_KEY"]) < 32:
            raise ValueError("SECRET_KEY must contain at least 32 characters")
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    app.config.setdefault("SESSION_COOKIE_SECURE", False)
    app.permanent_session_lifetime = timedelta(hours=8)
    limiter.init_app(app)
    app.register_blueprint(security)
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def guard_routes():
        if not app.config["AUTH_ENABLED"]:
            return None
        if request.endpoint in (
            "security.login_page", "security.login", "static", "health", "favicon",
        ):
            return None
        header = request.headers.get("Authorization", "")
        if header:
            if request.path.startswith("/api/v1/") and _bearer_authorized():
                return None
            return _api_error("Unauthorized", 401)
        if not session.get("authenticated"):
            if request.path.startswith("/api/v1/"):
                return _api_error("Unauthorized", 401)
            return redirect(url_for("security.login_page"))
        if request.method not in ("GET", "HEAD", "OPTIONS") and not _csrf_valid():
            if request.path.startswith("/api/v1/"):
                return _api_error("Invalid or missing CSRF token", 403)
            abort(403)
        return None

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # Inline CSS width indicators remain in the existing templates.
        # All executable JavaScript is external and restricted to same-origin.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'; form-action 'self'"
        )
        if app.config["AUTH_ENABLED"] and request.endpoint != "static":
            response.headers["Cache-Control"] = "private, no-store"
        return response

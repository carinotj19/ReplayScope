# ReplayScope security configuration

This document describes **optional single-operator access**, not a production
multi-tenant authentication system.

## Design goals

- Preserve the existing zero-configuration, localhost-only SQLite demo.
- Protect all dashboard and API reads/writes when opted in.
- Prevent cross-site form/JS requests from making unauthorized session writes.
- Support programmatic API clients separately from the browser session.
- Fail fast when protected mode is enabled without required secrets.

## Configuration

Environment variables:

| Variable | Meaning |
| --- | --- |
| REPLAYSCOPE_AUTH_ENABLED | Set to 1 to require authentication |
| REPLAYSCOPE_SECRET_KEY | Random stable secret, at least 32 characters |
| REPLAYSCOPE_ADMIN_PASSWORD_HASH | Output of werkzeug.security.generate_password_hash |
| REPLAYSCOPE_API_TOKEN | Optional long random bearer token for API integrations |
| REPLAYSCOPE_SECURE_COOKIE | Set to 1 only when HTTPS is in place |
| REPLAYSCOPE_RATE_STORAGE_URL | Flask-Limiter storage URI; defaults to memory:// |

PowerShell single-session protected test:

    $env:REPLAYSCOPE_SECRET_KEY = py -c "import secrets; print(secrets.token_urlsafe(48))"
    $env:REPLAYSCOPE_ADMIN_PASSWORD_HASH = py -c "import getpass; from werkzeug.security import generate_password_hash; print(generate_password_hash(getpass.getpass('New admin password: ')))"
    $env:REPLAYSCOPE_AUTH_ENABLED = "1"
    py -m flask --app replayscope:create_app run --debug

Do not place passwords, bearer tokens or session secrets in Git or screenshots.

## Request behavior

- GET /health and static assets remain publicly accessible.
- All other dashboard paths redirect unauthenticated users to GET /login.
- The /api/v1 routes return HTTP 401 JSON for unauthenticated requests.
- Cookie-authenticated browser actions require a session CSRF token on writes.
- POST /login itself requires its own CSRF token.
- API bearer token requests bypass session CSRF, but bearer access is limited
  to API routes; invalid Authorization headers are rejected.
- POST /logout requires CSRF and clears session authentication.
- Login attempts are throttled to 5 per minute per remote IP; upload requests
  to 30 per hour per IP when authentication is enabled.

## Boundaries and limitations

The current implementation supports ONE admin password. There are no
accounts, roles, audit trail, session revocation list, account recovery,
user-specific quotas, or multi-tenant data separation.

Rate-limit memory:// works for a single development process only. A public
multi-worker deployment must set REPLAYSCOPE_RATE_STORAGE_URL to a shared
backend such as Redis, and configure trusted reverse proxy handling correctly.
Do not trust arbitrary X-Forwarded-For client values.

The current content security policy restricts JavaScript to same-origin
assets, but allows inline CSS for pre-existing percentage bars and permits
Google Fonts requests. Consider self-hosting fonts and removing inline styles
before a public launch.

Only expose the application behind HTTPS with secure cookies, real secrets
management, request/access logging and a deployment-specific threat review.
Do not use Flask debug mode on any public interface. Existing local demo data
is unaffected by toggling REPLAYSCOPE_AUTH_ENABLED.

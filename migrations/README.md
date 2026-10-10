# Schema migrations

Managed installations use Flask-Migrate/Alembic. The initial revision is 0001_initial.

For a NEW EMPTY database, set DATABASE_URL and run:

    python -m flask --app replayscope:create_app db upgrade

The app uses AUTO_CREATE_DB=0 when DATABASE_URL is explicitly configured.

The default local SQLite development database is still created automatically to
preserve the existing dashboard workflow. Do not apply the initial schema-creation
migration to that already-populated SQLite database; it already has the tables.
For a new migration-managed SQLite install, point DATABASE_URL at an empty file.

Migration scripts are reviewed source code. Use flask db migrate only when
intentionally evolving the schema; inspect generated operations before applying.

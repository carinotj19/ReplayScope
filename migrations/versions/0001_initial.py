"""Initial ReplayScope schema for managed PostgreSQL/SQLite databases.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "experiments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "agent_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.UniqueConstraint("name", "version", name="uq_agent_version"),
    )
    op.create_table(
        "replay_uploads",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("experiment_id", sa.Integer(), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("format", sa.String(length=8), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("run_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(length=500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("experiment_id", "sha256", name="uq_experiment_upload_digest"),
    )
    op.create_index("ix_replay_uploads_experiment_id", "replay_uploads", ["experiment_id"])
    op.create_table(
        "benchmark_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("upload_id", sa.String(length=36), sa.ForeignKey("replay_uploads.id"), nullable=False),
        sa.Column("agent_version_id", sa.Integer(), sa.ForeignKey("agent_versions.id"), nullable=False),
        sa.Column("scenario", sa.String(length=120), nullable=False),
        sa.Column("seed", sa.String(length=80)),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("duration_ms", sa.Float()),
        sa.Column("failure_reason", sa.String(length=240)),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("events", sa.JSON(), nullable=False),
    )
    op.create_index("ix_benchmark_runs_upload_id", "benchmark_runs", ["upload_id"])
    op.create_index("ix_benchmark_runs_agent_version_id", "benchmark_runs", ["agent_version_id"])
    op.create_index("ix_benchmark_runs_scenario", "benchmark_runs", ["scenario"])


def downgrade():
    op.drop_index("ix_benchmark_runs_scenario", table_name="benchmark_runs")
    op.drop_index("ix_benchmark_runs_agent_version_id", table_name="benchmark_runs")
    op.drop_index("ix_benchmark_runs_upload_id", table_name="benchmark_runs")
    op.drop_table("benchmark_runs")
    op.drop_index("ix_replay_uploads_experiment_id", table_name="replay_uploads")
    op.drop_table("replay_uploads")
    op.drop_table("agent_versions")
    op.drop_table("experiments")

"""Add fenced upload leases without modifying existing uploads.

Revision ID: 0002_upload_leases
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_upload_leases"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "upload_leases",
        sa.Column("upload_id", sa.String(length=36),
                  sa.ForeignKey("replay_uploads.id"), primary_key=True),
        sa.Column("token", sa.String(length=36), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )
    op.create_index("ix_upload_leases_expires_at", "upload_leases", ["expires_at"])


def downgrade():
    op.drop_index("ix_upload_leases_expires_at", table_name="upload_leases")
    op.drop_table("upload_leases")

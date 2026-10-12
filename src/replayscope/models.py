"""Experiment data model. No simulation- or game-specific entities."""
from datetime import datetime, timezone
from uuid import uuid4

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint

db = SQLAlchemy()

def utcnow():
    return datetime.now(timezone.utc)

class Experiment(db.Model):
    __tablename__ = "experiments"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

class AgentVersion(db.Model):
    __tablename__ = "agent_versions"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_agent_version"),)
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    version = db.Column(db.String(80), nullable=False)

class ReplayUpload(db.Model):
    __tablename__ = "replay_uploads"
    __table_args__ = (UniqueConstraint("experiment_id", "sha256", name="uq_experiment_upload_digest"),)
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    experiment_id = db.Column(db.Integer, db.ForeignKey("experiments.id"), nullable=False, index=True)
    sha256 = db.Column(db.String(64), nullable=False)
    format = db.Column(db.String(8), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    path = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(24), nullable=False, default="queued")
    run_count = db.Column(db.Integer, nullable=False, default=0)
    error = db.Column(db.String(500))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

class BenchmarkRun(db.Model):
    __tablename__ = "benchmark_runs"
    id = db.Column(db.Integer, primary_key=True)
    upload_id = db.Column(db.String(36), db.ForeignKey("replay_uploads.id"), nullable=False, index=True)
    agent_version_id = db.Column(db.Integer, db.ForeignKey("agent_versions.id"), nullable=False, index=True)
    scenario = db.Column(db.String(120), nullable=False, index=True)
    seed = db.Column(db.String(80))
    outcome = db.Column(db.String(16), nullable=False)
    score = db.Column(db.Float, nullable=False)
    duration_ms = db.Column(db.Float)
    failure_reason = db.Column(db.String(240))
    extra = db.Column("metadata", db.JSON, nullable=False, default=dict)
    events = db.Column(db.JSON, nullable=False, default=list)
    agent_version = db.relationship("AgentVersion")

class UploadLease(db.Model):
    """Current fencing token and heartbeat for an in-progress upload.

    The separate table is intentional: db.create_all() adds it to legacy local
    SQLite databases without altering any existing upload or run record.
    """
    __tablename__ = "upload_leases"
    upload_id = db.Column(
        db.String(36), db.ForeignKey("replay_uploads.id"),
        primary_key=True,
    )
    token = db.Column(db.String(36), nullable=True)
    heartbeat_at = db.Column(db.DateTime(timezone=True), nullable=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)

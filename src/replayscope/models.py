from datetime import datetime, timezone
from uuid import uuid4

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint

db = SQLAlchemy()


class AgentVersion(db.Model):
    __tablename__ = "agent_versions"
    __table_args__ = (UniqueConstraint("name", "version"),)
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    version = db.Column(db.String(80), nullable=False)


class Experiment(db.Model):
    __tablename__ = "experiments"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, unique=True)


class Replay(db.Model):
    __tablename__ = "replays"
    __table_args__ = (
        UniqueConstraint("experiment_id", "agent_version_id", "player_slot", "digest"),
    )
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    experiment_id = db.Column(db.Integer, db.ForeignKey("experiments.id"), nullable=False)
    agent_version_id = db.Column(db.Integer, db.ForeignKey("agent_versions.id"), nullable=False)
    player_slot = db.Column(db.Integer, nullable=False)
    digest = db.Column(db.String(64), nullable=False)
    path = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="queued")
    metrics = db.Column(db.JSON)
    error = db.Column(db.String(500))
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    agent_version = db.relationship("AgentVersion")

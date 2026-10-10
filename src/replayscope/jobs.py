"""Worker entrypoint shared by inline testing and Redis/RQ."""
from pathlib import Path

from .ingestion import DatasetError, parse_dataset
from .models import AgentVersion, BenchmarkRun, ReplayUpload, db

def process_upload(upload_id, app=None):
    if app is None:
        from . import create_app
        app = create_app()
    with app.app_context():
        upload = db.session.get(ReplayUpload, upload_id)
        if upload is None:
            raise ValueError("Unknown upload")
        if upload.status == "ready":
            return "ready"
        upload.status = "processing"
        upload.error = None
        db.session.commit()
        try:
            records = parse_dataset(Path(upload.path).read_bytes(), upload.format)
            db.session.query(BenchmarkRun).filter_by(upload_id=upload.id).delete()
            versions = {}
            for record in records:
                key = (record.agent, record.version)
                if key not in versions:
                    agent = db.session.query(AgentVersion).filter_by(
                        name=record.agent, version=record.version
                    ).first()
                    if agent is None:
                        agent = AgentVersion(name=record.agent, version=record.version)
                        db.session.add(agent)
                        db.session.flush()
                    versions[key] = agent.id
                db.session.add(BenchmarkRun(
                    upload_id=upload.id, agent_version_id=versions[key],
                    scenario=record.scenario, seed=record.seed,
                    outcome=record.outcome, score=record.score,
                    duration_ms=record.duration_ms,
                    failure_reason=record.failure_reason,
                    extra=record.metadata, events=record.events,
                ))
            upload.status = "ready"
            upload.run_count = len(records)
            db.session.commit()
            return "ready"
        except (DatasetError, OSError, ValueError, TypeError) as exc:
            db.session.rollback()
            upload = db.session.get(ReplayUpload, upload_id)
            upload.status = "failed"
            upload.error = str(exc)[:500]
            db.session.commit()
            return "failed"
        except Exception:
            db.session.rollback()
            upload = db.session.get(ReplayUpload, upload_id)
            upload.status = "failed"
            upload.error = "Unexpected processing error"
            db.session.commit()
            raise

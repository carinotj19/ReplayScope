"""Flask application factory and routes for ReplayScope."""
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, request, current_app
from sqlalchemy.exc import IntegrityError

from .models import AgentVersion, Experiment, Replay, db
from .stats import summarize


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    db_url = os.getenv("DATABASE_URL") or "sqlite:///" + str(Path(app.instance_path) / "replayscope.sqlite3")
    if db_url.startswith("postgres://"):
        db_url = "postgresql://" + db_url[11:]
    app.config.update(
        SQLALCHEMY_DATABASE_URI=db_url, SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,
        UPLOAD_DIR=str(Path(app.instance_path) / "uploads"),
        REPLAYSCOPE_JOBS=os.getenv("REPLAYSCOPE_JOBS", "inline"),
        REDIS_URL=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    )
    if test_config:
        app.config.update(test_config)
    db.init_app(app)

    @app.get("/health")
    def health():
        return jsonify({"service": "replayscope", "status": "ok"})

    @app.post("/api/agent-versions")
    def add_agent_version():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="Expected JSON object"), 400
        name, version = str(data.get("name", "")).strip(), str(data.get("version", "")).strip()
        if not name or not version or len(name) > 120 or len(version) > 80:
            return jsonify(error="Name and version required"), 400
        item = AgentVersion(name=name, version=version)
        db.session.add(item)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify(error="Version already registered"), 409
        return jsonify(id=item.id, name=name, version=version), 201

    @app.get("/api/agent-versions")
    def list_agent_versions():
        return jsonify([{"id": a.id, "name": a.name, "version": a.version}
                        for a in db.session.query(AgentVersion).order_by(AgentVersion.id).all()])

    @app.post("/api/experiments")
    def add_experiment():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="Expected JSON object"), 400
        name = str(data.get("name", "")).strip()
        if not name or len(name) > 160:
            return jsonify(error="Experiment name required"), 400
        item = Experiment(name=name)
        db.session.add(item)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify(error="Experiment already exists"), 409
        return jsonify(id=item.id, name=item.name), 201

    @app.get("/api/experiments")
    def list_experiments():
        return jsonify([{"id": e.id, "name": e.name}
                        for e in db.session.query(Experiment).order_by(Experiment.id).all()])

    def replay_view(replay):
        return {
            "id": replay.id, "experiment_id": replay.experiment_id,
            "agent_version_id": replay.agent_version_id, "player_slot": replay.player_slot,
            "status": replay.status, "metrics": replay.metrics, "error": replay.error,
        }

    @app.post("/api/replays")
    def upload_replay():
        file = request.files.get("file")
        if not file or not file.filename or not file.filename.lower().endswith(".json"):
            return jsonify(error="A .json replay file is required"), 400
        try:
            exp_id, agent_id, slot = (int(request.form[key]) for key in
                                      ("experiment_id", "agent_version_id", "player_slot"))
        except (KeyError, ValueError, TypeError):
            return jsonify(error="Integer experiment_id, agent_version_id, player_slot required"), 400
        if not 0 <= slot < 4:
            return jsonify(error="Invalid player slot"), 400
        if not db.session.get(Experiment, exp_id) or not db.session.get(AgentVersion, agent_id):
            return jsonify(error="Experiment or agent version not found"), 404
        raw = file.read()
        if not raw:
            return jsonify(error="Empty replay"), 400
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return jsonify(error="Invalid JSON"), 400
        if not isinstance(payload, dict) or not isinstance(payload.get("steps"), list):
            return jsonify(error="Expected replay object with steps array"), 400
        digest = hashlib.sha256(raw).hexdigest()
        previous = db.session.query(Replay).filter_by(
            experiment_id=exp_id, agent_version_id=agent_id, player_slot=slot, digest=digest,
        ).first()
        if previous:
            return jsonify(replay_view(previous)), 200

        folder = Path(current_app.config["UPLOAD_DIR"])
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (str(uuid4()) + ".json")
        path.write_bytes(raw)
        replay = Replay(experiment_id=exp_id, agent_version_id=agent_id, player_slot=slot,
                        digest=digest, path=str(path), status="queued")
        db.session.add(replay)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            path.unlink(missing_ok=True)
            return jsonify(error="Duplicate replay"), 409

        if current_app.config["REPLAYSCOPE_JOBS"] == "rq":
            try:
                from redis import Redis
                from rq import Queue
                queue = Queue("replay-analysis", connection=Redis.from_url(current_app.config["REDIS_URL"]))
                queue.enqueue("replayscope.jobs.process_replay", replay.id)
            except Exception:
                replay.status = "failed"
                replay.error = "Could not enqueue analysis job"
                db.session.commit()
                return jsonify(replay_view(replay)), 503
        else:
            from .jobs import process_replay
            process_replay(replay.id, current_app._get_current_object())
            db.session.refresh(replay)
        return jsonify(replay_view(replay)), 201

    @app.get("/api/replays/<replay_id>")
    def get_replay(replay_id):
        replay = db.session.get(Replay, replay_id)
        return jsonify(replay_view(replay)) if replay else (jsonify(error="Not found"), 404)

    @app.get("/api/experiments/<int:experiment_id>/summary")
    def experiment_summary(experiment_id):
        if db.session.get(Experiment, experiment_id) is None:
            return jsonify(error="Experiment not found"), 404
        records = db.session.query(Replay).filter_by(experiment_id=experiment_id).all()
        groups = {}
        for record in records:
            group = groups.setdefault(record.agent_version_id, {
                "agent_version_id": record.agent_version_id,
                "name": record.agent_version.name, "version": record.agent_version.version,
                "metrics": [], "not_ready": 0,
            })
            if record.status == "ready" and record.metrics is not None:
                group["metrics"].append(record.metrics)
            else:
                group["not_ready"] += 1
        result = []
        for group in groups.values():
            rows = group.pop("metrics")
            result.append({**group, "overall": summarize(rows),
                           "by_mode": {mode: summarize([r for r in rows if r["mode"] == mode])
                                       for mode in ("2P", "4P")}})
        return jsonify(experiment_id=experiment_id, versions=result)

    with app.app_context():
        db.create_all()  # Development bootstrap only; add Alembic before production.
    return app

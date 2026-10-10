"""Flask HTTP layer for experiments, dataset uploads and performance analytics."""
import hashlib
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import IntegrityError

from .ingestion import DatasetError, parse_dataset
from .models import AgentVersion, BenchmarkRun, Experiment, ReplayUpload, db
from .stats import summarize

api = Blueprint("api", __name__)

def error(message, status=400):
    return jsonify({"error": message}), status

def upload_view(upload):
    return {
        "id": upload.id, "experiment_id": upload.experiment_id,
        "filename": upload.filename, "format": upload.format,
        "status": upload.status, "run_count": upload.run_count,
        "error": upload.error,
    }

def run_view(run):
    return {
        "id": run.id, "upload_id": run.upload_id,
        "agent_version_id": run.agent_version_id,
        "agent": run.agent_version.name, "version": run.agent_version.version,
        "scenario": run.scenario, "seed": run.seed, "outcome": run.outcome,
        "score": run.score, "duration_ms": run.duration_ms,
        "failure_reason": run.failure_reason,
        "metadata": run.extra, "events": run.events,
    }

@api.post("/experiments")
def create_experiment():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error("Expected a JSON object")
    name = data.get("name")
    description = data.get("description", "")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 160:
        return error("name must be nonempty text (max 160 characters)")
    if not isinstance(description, str) or len(description) > 4000:
        return error("description must be text (max 4000 characters)")
    item = Experiment(name=name.strip(), description=description)
    db.session.add(item)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error("Experiment name already exists", 409)
    return jsonify({"id": item.id, "name": item.name, "description": item.description}), 201

@api.get("/experiments")
def list_experiments():
    items = db.session.query(Experiment).order_by(Experiment.id).all()
    return jsonify([{"id": e.id, "name": e.name, "description": e.description} for e in items])

@api.get("/agent-versions")
def list_agent_versions():
    versions = db.session.query(AgentVersion).order_by(AgentVersion.id).all()
    return jsonify([{"id": a.id, "name": a.name, "version": a.version} for a in versions])

@api.post("/uploads")
def upload_dataset():
    file = request.files.get("file")
    if file is None or not file.filename:
        return error("Multipart field 'file' is required")
    format_name = Path(file.filename).suffix.lower().lstrip(".")
    if format_name not in ("json", "csv"):
        return error("Only .json and .csv are supported")
    try:
        experiment_id = int(request.form["experiment_id"])
    except (KeyError, ValueError, TypeError):
        return error("experiment_id must be an integer")
    if db.session.get(Experiment, experiment_id) is None:
        return error("Experiment not found", 404)
    raw = file.read()
    if not raw:
        return error("Empty dataset")
    try:
        parse_dataset(raw, format_name)  # fail fast before storing
    except DatasetError as exc:
        return error(str(exc), 422)
    digest = hashlib.sha256(raw).hexdigest()
    previous = db.session.query(ReplayUpload).filter_by(
        experiment_id=experiment_id, sha256=digest
    ).first()
    if previous:
        return jsonify(upload_view(previous)), 200

    folder = Path(current_app.config["UPLOAD_DIR"])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid4()}.{format_name}"
    path.write_bytes(raw)
    upload = ReplayUpload(
        experiment_id=experiment_id, filename=Path(file.filename).name[:255],
        sha256=digest, format=format_name, path=str(path), status="queued",
    )
    db.session.add(upload)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        path.unlink(missing_ok=True)
        return error("Duplicate upload", 409)

    if current_app.config["PROCESSING_MODE"] == "rq":
        try:
            from redis import Redis
            from rq import Queue
            queue = Queue(
                "replayscope",
                connection=Redis.from_url(current_app.config["REDIS_URL"]),
            )
            queue.enqueue("replayscope.jobs.process_upload", upload.id)
        except Exception:
            upload.status = "failed"
            upload.error = "Could not enqueue background processing"
            db.session.commit()
            return jsonify(upload_view(upload)), 503
    else:
        from .jobs import process_upload
        process_upload(upload.id, current_app._get_current_object())
        db.session.refresh(upload)
    return jsonify(upload_view(upload)), 201

@api.get("/uploads/<upload_id>")
def get_upload(upload_id):
    upload = db.session.get(ReplayUpload, upload_id)
    if upload is None:
        return error("Upload not found", 404)
    return jsonify(upload_view(upload))

def _run_query(experiment_id):
    return db.session.query(BenchmarkRun).join(ReplayUpload).filter(
        ReplayUpload.experiment_id == experiment_id,
        ReplayUpload.status == "ready",
    )

@api.get("/experiments/<int:experiment_id>/runs")
def list_runs(experiment_id):
    if db.session.get(Experiment, experiment_id) is None:
        return error("Experiment not found", 404)
    try:
        page = int(request.args.get("page", "1"))
        per_page = int(request.args.get("per_page", "25"))
    except ValueError:
        return error("page and per_page must be integers")
    if page < 1 or not 1 <= per_page <= 100:
        return error("page must be positive; per_page must be 1 to 100")
    query = _run_query(experiment_id)
    if request.args.get("scenario"):
        query = query.filter(BenchmarkRun.scenario == request.args["scenario"])
    if request.args.get("agent_version_id"):
        try:
            version_id = int(request.args["agent_version_id"])
        except ValueError:
            return error("agent_version_id must be an integer")
        query = query.filter(BenchmarkRun.agent_version_id == version_id)
    total = query.count()
    records = query.order_by(BenchmarkRun.id).offset((page - 1) * per_page).limit(per_page).all()
    return jsonify({"total": total, "page": page, "per_page": per_page,
                    "items": [run_view(run) for run in records]})

@api.get("/experiments/<int:experiment_id>/summary")
def experiment_summary(experiment_id):
    if db.session.get(Experiment, experiment_id) is None:
        return error("Experiment not found", 404)
    query = _run_query(experiment_id)
    scenario = request.args.get("scenario")
    if scenario:
        query = query.filter(BenchmarkRun.scenario == scenario)
    grouped = {}
    for run in query.all():
        group = grouped.setdefault(run.agent_version_id, {
            "agent_version_id": run.agent_version_id,
            "agent": run.agent_version.name,
            "version": run.agent_version.version,
            "rows": [], "scenarios": {},
        })
        group["rows"].append(run)
        group["scenarios"].setdefault(run.scenario, []).append(run)
    versions = []
    for group in grouped.values():
        rows = group.pop("rows")
        scenarios = group.pop("scenarios")
        versions.append({
            **group, "overall": summarize(rows),
            "by_scenario": {key: summarize(value)
                            for key, value in sorted(scenarios.items())},
        })
    versions.sort(key=lambda row: (row["agent"], row["version"]))
    return jsonify({"experiment_id": experiment_id, "versions": versions,
                    "scope": {"scenario": scenario}})


@api.get("/experiments/<int:experiment_id>/compare")
def paired_comparison(experiment_id):
    """Compare two versions of one agent using exact scenario/seed matches."""
    from .comparisons import ComparisonError, compare_versions

    try:
        baseline = int(request.args["baseline_id"])
        candidate = int(request.args["candidate_id"])
    except (KeyError, ValueError, TypeError):
        return error("baseline_id and candidate_id must be integer query parameters")
    scenario = request.args.get("scenario", "").strip() or None
    try:
        result = compare_versions(experiment_id, baseline, candidate, scenario=scenario)
    except LookupError as exc:
        return error(str(exc), 404)
    except ComparisonError as exc:
        return error(str(exc), 400)
    return jsonify(result)

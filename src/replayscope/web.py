"""Server-rendered portfolio dashboard. The JSON API remains the data ingestion boundary."""
from collections import defaultdict
from math import ceil

from flask import Blueprint, abort, render_template, request
from sqlalchemy import func

from .models import AgentVersion, BenchmarkRun, Experiment, ReplayUpload, db
from .stats import summarize

web = Blueprint("web", __name__)


@web.get("/")
def home():
    experiments = db.session.query(Experiment).order_by(Experiment.created_at.desc(), Experiment.id.desc()).all()
    counts = dict(
        db.session.query(ReplayUpload.experiment_id, func.count(BenchmarkRun.id))
        .join(BenchmarkRun, BenchmarkRun.upload_id == ReplayUpload.id)
        .filter(ReplayUpload.status == "ready")
        .group_by(ReplayUpload.experiment_id).all()
    )
    uploads = db.session.query(ReplayUpload).order_by(ReplayUpload.created_at.desc()).limit(5).all()
    total_runs = sum(counts.values())
    return render_template(
        "home.html",
        active_page="home", experiments=experiments, counts=counts,
        recent_uploads=uploads, total_runs=total_runs,
    )


@web.get("/experiments/<int:experiment_id>")
def experiment_page(experiment_id):
    experiment = db.session.get(Experiment, experiment_id)
    if experiment is None:
        abort(404)

    scope = request.args.get("scenario", "").strip()
    if len(scope) > 120:
        abort(400)

    ready = db.session.query(BenchmarkRun).join(
        ReplayUpload, ReplayUpload.id == BenchmarkRun.upload_id
    ).filter(
        ReplayUpload.experiment_id == experiment_id,
        ReplayUpload.status == "ready",
    )

    all_scenarios = [
        item[0] for item in ready.with_entities(BenchmarkRun.scenario)
        .distinct().order_by(BenchmarkRun.scenario).all()
    ]
    if scope:
        ready = ready.filter(BenchmarkRun.scenario == scope)

    rows = ready.order_by(BenchmarkRun.id).all()
    groups = defaultdict(list)
    for row in rows:
        groups[(row.agent_version.name, row.agent_version.version, row.agent_version_id)].append(row)

    versions = []
    for (name, version, version_id), group in sorted(groups.items()):
        metric = summarize(group)
        primary_rate = metric["game_win_rate"]
        metric_label = "Game win rate"
        if primary_rate is None:
            primary_rate = metric["task_success_rate"]
            metric_label = "Task success rate" if primary_rate is not None else "No rate"
        versions.append({
            "agent": name,
            "version": version,
            "agent_version_id": version_id,
            "metrics": metric,
            "primary_rate": primary_rate,
            "metric_label": metric_label,
        })

    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        abort(400)
    per_page = 20
    total_pages = max(1, ceil(len(rows) / per_page))
    page = min(page, total_pages)
    shown = rows[(page - 1) * per_page: page * per_page]
    uploads = db.session.query(ReplayUpload).filter_by(
        experiment_id=experiment_id
    ).order_by(ReplayUpload.created_at.desc(), ReplayUpload.id.desc()).limit(15).all()

    return render_template(
        "experiment.html",
        active_page="experiments", experiment=experiment,
        versions=versions, scenarios=all_scenarios, scope=scope, rows=shown,
        uploads=uploads, page=page, total_pages=total_pages,
        total_runs=len(rows), all_total=len(all_scenarios),
        mean_score=sum(row.score for row in rows) / len(rows) if rows else None,
    )


@web.get("/experiments/<int:experiment_id>/compare")
def compare_page(experiment_id):
    from .comparisons import ComparisonError, available_versions, compare_versions

    experiment = db.session.get(Experiment, experiment_id)
    if experiment is None:
        abort(404)

    versions = available_versions(experiment_id)
    available_scenarios = (
        db.session.query(BenchmarkRun.scenario)
        .join(ReplayUpload, ReplayUpload.id == BenchmarkRun.upload_id)
        .filter(ReplayUpload.experiment_id == experiment_id, ReplayUpload.status == "ready")
        .distinct().order_by(BenchmarkRun.scenario).all()
    )
    scenarios = [item[0] for item in available_scenarios]
    scenario = request.args.get("scenario", "").strip()
    if len(scenario) > 120:
        abort(400)

    groups = defaultdict(list)
    for version in versions:
        groups[version.name].append(version)
    default_pair = next((items[:2] for items in groups.values() if len(items) > 1), None)

    baseline_text = request.args.get("baseline_id")
    candidate_text = request.args.get("candidate_id")
    if baseline_text is None and candidate_text is None:
        baseline = default_pair[0].id if default_pair else None
        candidate = default_pair[1].id if default_pair else None
    else:
        try:
            baseline = int(baseline_text)
            candidate = int(candidate_text)
        except (TypeError, ValueError):
            abort(400)
    comparison = None
    error = None
    if baseline is not None and candidate is not None:
        try:
            comparison = compare_versions(
                experiment_id, baseline, candidate, scenario=scenario or None
            )
        except ComparisonError as exc:
            error = str(exc)
    return render_template(
        "comparison.html",
        active_page="experiments",
        experiment=experiment, versions=versions, scenarios=scenarios,
        baseline=baseline, candidate=candidate, scenario=scenario,
        comparison=comparison, comparison_error=error,
    )

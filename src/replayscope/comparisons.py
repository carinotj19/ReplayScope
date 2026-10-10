"""Seed-matched version comparisons; no unearned significance claims.

A pair must belong to the same experiment, same agent, scenario and seed.
Ambiguous duplicate keys are excluded. The score delta assumes a larger
numeric score is preferable, but is purely descriptive.
"""
from collections import defaultdict
from statistics import mean, median

from .models import AgentVersion, BenchmarkRun, Experiment, ReplayUpload, db


class ComparisonError(ValueError):
    """Invalid or incomparable agent-version selection."""


def available_versions(experiment_id):
    return (
        db.session.query(AgentVersion)
        .join(BenchmarkRun, BenchmarkRun.agent_version_id == AgentVersion.id)
        .join(ReplayUpload, ReplayUpload.id == BenchmarkRun.upload_id)
        .filter(
            ReplayUpload.experiment_id == experiment_id,
            ReplayUpload.status == "ready",
        )
        .distinct()
        .order_by(AgentVersion.name, AgentVersion.version, AgentVersion.id)
        .all()
    )


def _value(run, key):
    return run[key] if isinstance(run, dict) else getattr(run, key)


def _metrics(pairs):
    deltas = [p["score_delta"] for p in pairs]
    timed = [p["duration_delta_ms"] for p in pairs if p["duration_delta_ms"] is not None]
    return {
        "pairs": len(pairs),
        "mean_score_delta": mean(deltas) if deltas else None,
        "median_score_delta": median(deltas) if deltas else None,
        "higher_score": sum(delta > 0 for delta in deltas),
        "equal_score": sum(delta == 0 for delta in deltas),
        "lower_score": sum(delta < 0 for delta in deltas),
        "mean_duration_delta_ms": mean(timed) if timed else None,
        "timed_pairs": len(timed),
    }


def compare_runs(runs, baseline_id, candidate_id):
    """Evaluate unique overlapping (scenario, seed) keys only.

    Missing seeds are never paired; duplicate keys on either side are
    ambiguous and intentionally discarded instead of arbitrarily matched.
    """
    index = {baseline_id: defaultdict(list), candidate_id: defaultdict(list)}
    unseeded = {baseline_id: 0, candidate_id: 0}
    for row in runs:
        version = _value(row, "agent_version_id")
        if version not in index:
            continue
        seed = _value(row, "seed")
        if seed is None or seed == "":
            unseeded[version] += 1
            continue
        index[version][(_value(row, "scenario"), str(seed))].append(row)

    base = index[baseline_id]
    cand = index[candidate_id]
    base_keys = set(base)
    cand_keys = set(cand)
    overlap = base_keys & cand_keys
    ambiguous = {key for key in overlap if len(base[key]) != 1 or len(cand[key]) != 1}

    pairs = []
    by_scenario = defaultdict(list)
    for scenario, seed in sorted(overlap - ambiguous):
        left = base[(scenario, seed)][0]
        right = cand[(scenario, seed)][0]
        left_duration = _value(left, "duration_ms")
        right_duration = _value(right, "duration_ms")
        pair = {
            "scenario": scenario, "seed": seed,
            "baseline_score": _value(left, "score"),
            "candidate_score": _value(right, "score"),
            "score_delta": _value(right, "score") - _value(left, "score"),
            "baseline_outcome": _value(left, "outcome"),
            "candidate_outcome": _value(right, "outcome"),
            "duration_delta_ms": (
                right_duration - left_duration
                if right_duration is not None and left_duration is not None
                else None
            ),
        }
        pairs.append(pair)
        by_scenario[scenario].append(pair)

    return {
        "baseline_id": baseline_id,
        "candidate_id": candidate_id,
        "overall": _metrics(pairs),
        "by_scenario": {
            scenario: _metrics(items) for scenario, items in sorted(by_scenario.items())
        },
        "excluded": {
            "baseline_unseeded": unseeded[baseline_id],
            "candidate_unseeded": unseeded[candidate_id],
            "baseline_only_keys": len(base_keys - cand_keys),
            "candidate_only_keys": len(cand_keys - base_keys),
            "ambiguous_overlap_keys": len(ambiguous),
        },
        "pair_sample": pairs[:50],
        "pair_sample_truncated": len(pairs) > 50,
    }


def compare_versions(experiment_id, baseline_id, candidate_id, scenario=None):
    """Validate versions and compare ready runs inside one experiment."""
    if db.session.get(Experiment, experiment_id) is None:
        raise LookupError("Experiment not found")
    if baseline_id == candidate_id:
        raise ComparisonError("Select two different agent versions")
    base = db.session.get(AgentVersion, baseline_id)
    cand = db.session.get(AgentVersion, candidate_id)
    if base is None or cand is None:
        raise ComparisonError("Agent version not found")
    if base.name != cand.name:
        raise ComparisonError("Compare versions of the same agent")
    if scenario is not None and len(scenario) > 120:
        raise ComparisonError("Scenario filter is too long")

    query = (
        db.session.query(BenchmarkRun)
        .join(ReplayUpload, ReplayUpload.id == BenchmarkRun.upload_id)
        .filter(
            ReplayUpload.experiment_id == experiment_id,
            ReplayUpload.status == "ready",
            BenchmarkRun.agent_version_id.in_((baseline_id, candidate_id)),
        )
    )
    if scenario:
        query = query.filter(BenchmarkRun.scenario == scenario)
    runs = query.order_by(BenchmarkRun.id).all()
    present = {r.agent_version_id for r in runs}
    if baseline_id not in present or candidate_id not in present:
        raise ComparisonError("Both agent versions need ready runs in this scope")
    result = compare_runs(runs, baseline_id, candidate_id)
    result["experiment_id"] = experiment_id
    result["agent"] = base.name
    result["baseline_version"] = base.version
    result["candidate_version"] = cand.version
    result["scenario"] = scenario or None
    return result

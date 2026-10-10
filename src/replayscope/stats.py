"""Descriptive statistics. Wilson intervals assume independent observations."""
from collections import Counter
from math import sqrt

def wilson_interval(wins, trials, z=1.959963984540054):
    if trials <= 0:
        return None
    p = wins / trials
    denominator = 1 + z * z / trials
    center = (p + z * z / (2 * trials)) / denominator
    half = z * sqrt(p * (1-p) / trials + z*z / (4*trials*trials)) / denominator
    return [max(0.0, center-half), min(1.0, center+half)]

def summarize(runs):
    rows = list(runs)
    def get(row, attr):
        return row[attr] if isinstance(row, dict) else getattr(row, attr)
    counts = Counter(get(row, "outcome") for row in rows)
    games = counts["win"] + counts["loss"] + counts["draw"]
    tasks = counts["success"] + counts["failure"]
    durations = [get(row, "duration_ms") for row in rows if get(row, "duration_ms") is not None]
    failures = Counter(get(row, "failure_reason") for row in rows
                       if get(row, "outcome") in ("loss", "failure") and get(row, "failure_reason"))
    return {
        "runs": len(rows),
        "outcomes": {k: counts[k] for k in ("win", "loss", "draw", "success", "failure")},
        "game_win_rate": counts["win"] / games if games else None,
        "game_win_rate_95pct_wilson": wilson_interval(counts["win"], games),
        "task_success_rate": counts["success"] / tasks if tasks else None,
        "task_success_rate_95pct_wilson": wilson_interval(counts["success"], tasks),
        "mean_score": sum(get(row, "score") for row in rows) / len(rows) if rows else None,
        "mean_duration_ms": sum(durations) / len(durations) if durations else None,
        "failure_reasons": dict(failures.most_common()),
    }

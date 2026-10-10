from math import sqrt


def wilson(wins, n, z=1.959963984540054):
    if n == 0:
        return None
    p = wins / n
    denominator = 1 + z * z / n
    midpoint = (p + z * z / (2 * n)) / denominator
    half = z * sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denominator
    return [max(0.0, midpoint - half), min(1.0, midpoint + half)]


def summarize(rows):
    n = len(rows)
    wins = sum(r["outcome"] == "win" for r in rows)
    draws = sum(r["outcome"] == "draw" for r in rows)
    return {
        "games": n, "wins": wins, "draws": draws, "losses": n - wins - draws,
        "win_rate": wins / n if n else None, "win_rate_95pct_wilson": wilson(wins, n),
        "mean_final_score": sum(r["final_score"] for r in rows) / n if n else None,
    }

import json

import pytest

from replayscope.ingestion import DatasetError, parse_dataset
from replayscope.stats import summarize, wilson_interval


def fixture_data():
    return {"runs": [
        {"agent": "Alpha", "version": "v1", "scenario": "navigation", "seed": 0,
         "outcome": "success", "score": 0.8, "duration_ms": 100,
         "events": [{"type": "move", "step": 1}]},
        {"agent": "Beta", "version": "v2", "scenario": "navigation",
         "outcome": "failure", "score": 0, "failure_reason": "timeout"},
    ]}


def test_json_parses_events_and_zero_seed():
    rows = parse_dataset(json.dumps(fixture_data()).encode(), "json")
    assert len(rows) == 2
    assert rows[0].seed == "0"
    assert rows[0].events[0]["type"] == "move"
    assert rows[1].score == 0


def test_csv_import():
    raw = b"agent,version,scenario,outcome,score,duration_ms\nAlpha,v1,maze,win,42,200\n"
    rows = parse_dataset(raw, "csv")
    assert rows[0].score == 42
    assert rows[0].duration_ms == 200
    assert rows[0].outcome == "win"


@pytest.mark.parametrize("change", [
    {"agent": ""},
    {"outcome": "unknown"},
    {"score": "NaN"},
    {"score": "inf"},
    {"score": True},
    {"duration_ms": -3},
    {"events": ["not an event"]},
])
def test_rejects_invalid_run(change):
    row = fixture_data()["runs"][0]
    row.update(change)
    with pytest.raises(DatasetError):
        parse_dataset(json.dumps({"runs": [row]}).encode(), "json")


def test_csv_headers_are_validated():
    with pytest.raises(DatasetError):
        parse_dataset(b"agent,outcome\nOne,win\n", "csv")


def test_separate_game_and_task_rates():
    rows = [
        {"outcome": "win", "score": 10, "duration_ms": 100, "failure_reason": None},
        {"outcome": "draw", "score": 5, "duration_ms": None, "failure_reason": None},
        {"outcome": "success", "score": 9, "duration_ms": 200, "failure_reason": None},
        {"outcome": "failure", "score": 0, "duration_ms": 300, "failure_reason": "timeout"},
    ]
    result = summarize(rows)
    assert result["game_win_rate"] == 0.5
    assert result["task_success_rate"] == 0.5
    assert result["mean_score"] == 6
    assert result["mean_duration_ms"] == 200
    assert result["failure_reasons"] == {"timeout": 1}
    assert wilson_interval(0, 0) is None
    lower, upper = wilson_interval(5, 10)
    assert lower < 0.5 < upper

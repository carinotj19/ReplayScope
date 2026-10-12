"""Pure-Python parser for generic AI-agent benchmark datasets."""
import csv
import io
import json
import math
from dataclasses import dataclass

ALLOWED_OUTCOMES = frozenset({"win", "loss", "draw", "success", "failure"})
MAX_RUNS = 2000
MAX_EVENTS_PER_RUN = 500
MAX_NESTING_DEPTH = 10
MAX_NESTED_NODES = 6000
MAX_NESTED_STRING = 2048
MAX_NESTED_KEY = 128

class DatasetError(ValueError):
    """Invalid user-provided benchmark input."""

@dataclass(frozen=True)
class RunData:
    agent: str
    version: str
    scenario: str
    outcome: str
    score: float
    seed: str | None
    duration_ms: float | None
    failure_reason: str | None
    metadata: dict
    events: list

def _text(row, key, limit, required=True):
    value = row.get(key)
    if value is None or value == "":
        if required:
            raise DatasetError(f"{key} is required")
        return None
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise DatasetError(f"{key} must be nonempty text (max {limit} characters)")
    return value.strip()

def _number(row, key, required=True, nonnegative=False):
    value = row.get(key)
    if value is None or value == "":
        if required:
            raise DatasetError(f"{key} is required")
        return None
    if isinstance(value, bool):
        raise DatasetError(f"{key} must be a finite number")
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise DatasetError(f"{key} must be a finite number") from exc
    if not math.isfinite(number) or (nonnegative and number < 0):
        raise DatasetError(f"{key} must be a finite {'nonnegative ' if nonnegative else ''}number")
    return number

def _validate_nested(value, field):
    """Iteratively bound arbitrary metadata/trace structures before storage.

    The limit applies to each run's complete nested payload. Iterative
    traversal avoids Python recursion limits on intentionally deep input.
    """
    stack = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_NESTED_NODES:
            raise DatasetError(f"{field} exceeds the nested value limit")
        if depth > MAX_NESTING_DEPTH:
            raise DatasetError(f"{field} exceeds maximum nesting depth")
        if isinstance(current, dict):
            if len(current) > 2000:
                raise DatasetError(f"{field} has too many object keys")
            for key, item in current.items():
                if not isinstance(key, str) or len(key) > MAX_NESTED_KEY:
                    raise DatasetError(f"{field} contains an invalid object key")
                stack.append((item, depth + 1))
        elif isinstance(current, list):
            if len(current) > MAX_NESTED_NODES:
                raise DatasetError(f"{field} contains an oversized array")
            stack.extend((item, depth + 1) for item in current)
        elif isinstance(current, str):
            if len(current) > MAX_NESTED_STRING:
                raise DatasetError(f"{field} contains an oversized string")
        elif isinstance(current, (float, int)) and not isinstance(current, bool):
            try:
                finite = math.isfinite(float(current))
            except (ValueError, TypeError, OverflowError):
                finite = False
            if not finite:
                raise DatasetError(f"{field} contains a nonfinite number")
        elif current is not None and not isinstance(current, bool):
            raise DatasetError(f"{field} contains an unsupported value")


def _run(row):
    if not isinstance(row, dict):
        raise DatasetError("Each run must be an object or CSV row")
    agent = _text(row, "agent", 120)
    version = _text(row, "version", 80)
    scenario = _text(row, "scenario", 120)
    outcome = _text(row, "outcome", 16).lower()
    if outcome not in ALLOWED_OUTCOMES:
        raise DatasetError("outcome must be win, loss, draw, success, or failure")
    seed = row.get("seed")
    if seed is None or seed == "":
        seed = None
    elif isinstance(seed, (str, int)) and not isinstance(seed, bool) and len(str(seed)) <= 80:
        seed = str(seed)
    else:
        raise DatasetError("seed must be text or integer (max 80 characters)")
    failure_reason = _text(row, "failure_reason", 240, required=False)
    metadata = row.get("metadata", {})
    events = row.get("events", [])
    if not isinstance(metadata, dict):
        raise DatasetError("metadata must be an object")
    if not isinstance(events, list) or len(events) > MAX_EVENTS_PER_RUN:
        raise DatasetError(f"events must be an array with at most {MAX_EVENTS_PER_RUN} entries")
    if any(not isinstance(e, dict) or not isinstance(e.get("type"), str) or not e["type"].strip() or len(e["type"]) > 120 for e in events):
        raise DatasetError("each event must contain a nonempty type string (max 120 characters)")
    _validate_nested({"metadata": metadata, "events": events}, "metadata/events")
    return RunData(
        agent=agent, version=version, scenario=scenario, outcome=outcome,
        score=_number(row, "score"), seed=seed,
        duration_ms=_number(row, "duration_ms", required=False, nonnegative=True),
        failure_reason=failure_reason, metadata=metadata, events=events,
    )

def parse_dataset(raw: bytes, file_format: str) -> list[RunData]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DatasetError("Dataset must use UTF-8 encoding") from exc
    if file_format == "json":
        try:
            payload = json.loads(text, parse_constant=lambda s: (_ for _ in ()).throw(DatasetError("Nonfinite JSON value")))
        except (ValueError, RecursionError) as exc:
            raise DatasetError("Invalid JSON") from exc
        rows = payload.get("runs") if isinstance(payload, dict) else payload
    elif file_format == "csv":
        try:
            reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
            if not reader.fieldnames or not {"agent", "version", "scenario", "outcome", "score"}.issubset(reader.fieldnames):
                raise DatasetError("CSV requires agent, version, scenario, outcome, score headers")
            if len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise DatasetError("CSV contains duplicate column headers")
            rows = list(reader)
            if any(None in row for row in rows):
                raise DatasetError("CSV contains extra columns")
        except csv.Error as exc:
            raise DatasetError("Invalid CSV") from exc
    else:
        raise DatasetError("Only .json and .csv are supported")
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_RUNS:
        raise DatasetError(f"Dataset must contain between 1 and {MAX_RUNS} runs")
    output = []
    for index, row in enumerate(rows, start=1):
        try:
            output.append(_run(row))
        except DatasetError as exc:
            raise DatasetError(f"Run {index}: {exc}") from exc
    return output

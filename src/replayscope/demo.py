"""Deterministic *synthetic* data for portfolio demos.

The generator is independent of external simulation engines and uses the
same dataset validator/processor as user uploads. Neither RNG nor network
calls nor third-party benchmark data are required.
"""
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import click
from flask import current_app

from .ingestion import parse_dataset
from .jobs import process_upload
from .models import Experiment, ReplayUpload, db


DEMO_TAG = "SYNTHETIC DEMO"
DEMO_GENERATOR_VERSION = "1"


def _navigation_runs():
    runs = []
    scenarios = ("maze-easy", "maze-medium", "maze-hard")
    for difficulty, scenario in enumerate(scenarios, start=1):
        for seed in range(1, 17):
            # Fixed arithmetic deliberately produces overlapping results and
            # mixed outcomes. Values are invented, not measurements.
            risk = (seed * 7 + difficulty * 3) % 10
            for candidate, version in ((False, "baseline"), (True, "candidate")):
                threshold = (2 + difficulty) - (1 if candidate else 0)
                success = risk >= threshold
                variation = (seed * 5 + difficulty * 2) % 13
                change = (7 if candidate else 0) - (11 if candidate and seed % 7 == 0 else 0)
                score = (74 - 5 * difficulty if success else 33 - 3 * difficulty) + variation + change
                duration = 460 + 195 * difficulty + 17 * seed - (42 if candidate else 0)
                outcome = "success" if success else "failure"
                runs.append({
                    "agent": "Navigator",
                    "version": version,
                    "scenario": scenario,
                    "seed": seed,
                    "outcome": outcome,
                    "score": score,
                    "duration_ms": duration,
                    **({"failure_reason": "timeout" if risk % 2 else "blocked_path"}
                       if not success else {}),
                    "metadata": {
                        "synthetic": True,
                        "generator_version": DEMO_GENERATOR_VERSION,
                        "difficulty": difficulty,
                        "challenge_type": "navigation",
                    },
                    "events": [
                        {"type": "start", "seed": seed},
                        {"type": "checkpoint", "progress": 50, "elapsed_ms": duration // 2},
                        {"type": "finish", "result": outcome, "elapsed_ms": duration},
                    ],
                })
    return runs


def _arena_runs():
    runs = []
    for scenario in ("arena-small", "arena-large"):
        arena_offset = 2 if scenario == "arena-large" else 0
        for seed in range(1, 13):
            roll = (seed * 11 + arena_offset * 3) % 10
            for candidate, version in ((False, "baseline"), (True, "candidate")):
                win_limit = 4 if candidate else 3
                outcome = "win" if roll < win_limit else "draw" if roll == 4 else "loss"
                score = (
                    {"win": 90, "draw": 58, "loss": 25}[outcome]
                    + (seed * 3 % 9)
                    + (4 if candidate else 0)
                )
                duration = 450 + arena_offset * 140 + seed * 31 - (18 if candidate else 0)
                runs.append({
                    "agent": "ArenaBot",
                    "version": version,
                    "scenario": scenario,
                    "seed": seed,
                    "outcome": outcome,
                    "score": score,
                    "duration_ms": duration,
                    **({"failure_reason": "opponent_advantage"} if outcome == "loss" else {}),
                    "metadata": {
                        "synthetic": True,
                        "generator_version": DEMO_GENERATOR_VERSION,
                        "challenge_type": "arena",
                    },
                    "events": [
                        {"type": "round_start", "seed": seed},
                        {"type": "round_end", "outcome": outcome},
                    ],
                })
    return runs


def build_demo_datasets():
    """Immutable, reproducible (name, description, bytes) fixtures."""
    cases = (
        (
            "SYNTHETIC DEMO — Navigation Trials",
            "Illustrative baseline and candidate runs on three maze scenarios; fixed paired seeds.",
            _navigation_runs(),
        ),
        (
            "SYNTHETIC DEMO — Arena Trials",
            "Illustrative competitive W/L/D outcomes on two arenas with matched seeds.",
            _arena_runs(),
        ),
    )
    output = []
    for name, description, runs in cases:
        raw = (json.dumps({"runs": runs}, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        parse_dataset(raw, "json")  # demo must obey our public ingestion contract
        output.append((name, description, raw))
    return tuple(output)


def seed_demo_data(*, dry_run=False):
    """Seed demo uploads exactly once per experiment and digest.

    Existing experiments, runs and files are never deleted or overwritten.
    A ready matching upload is reused. A previously failed matching upload
    may be retried using its already-stored source bytes.
    """
    results = []
    for name, description, raw in build_demo_datasets():
        record_count = len(json.loads(raw)["runs"])
        if dry_run:
            results.append((name, None, record_count, "dry-run"))
            continue

        experiment = db.session.query(Experiment).filter_by(name=name).one_or_none()
        if experiment is None:
            experiment = Experiment(name=name, description=description)
            db.session.add(experiment)
            db.session.commit()

        digest = hashlib.sha256(raw).hexdigest()
        upload = db.session.query(ReplayUpload).filter_by(
            experiment_id=experiment.id, sha256=digest
        ).one_or_none()
        if upload is None:
            folder = Path(current_app.config["UPLOAD_DIR"])
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{uuid4()}.json"
            path.write_bytes(raw)
            upload = ReplayUpload(
                experiment_id=experiment.id,
                sha256=digest,
                format="json",
                filename="synthetic-demo-v1.json",
                path=str(path),
                status="queued",
            )
            db.session.add(upload)
            db.session.commit()
            action = "created"
        else:
            action = "reused"

        if upload.status != "ready":
            state = process_upload(upload.id, current_app._get_current_object())
            if state != "ready":
                raise click.ClickException(f"Processing failed for {name}: {upload.error}")
        results.append((name, experiment.id, record_count, action))
    return results


def register_demo_cli(app):
    @app.cli.command("seed-demo")
    @click.option("--dry-run", is_flag=True, help="Show planned synthetic datasets without writing.")
    def seed_demo(dry_run):
        """Load reproducible synthetic demonstrations without clearing existing data."""
        click.echo("ReplayScope sample data is SYNTHETIC, not real benchmark evidence.")
        for name, experiment_id, run_count, action in seed_demo_data(dry_run=dry_run):
            suffix = f" /experiments/{experiment_id}" if experiment_id is not None else ""
            click.echo(f"[{action}] {name}: {run_count} runs{suffix}")

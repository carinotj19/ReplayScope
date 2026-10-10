import json
from pathlib import Path

from .models import db, Replay
from .orbit import analyze


def process_replay(replay_id, app=None):
    """RQ worker entrypoint. Inline mode supplies the Flask app explicitly."""
    if app is None:
        from . import create_app
        app = create_app()
    with app.app_context():
        replay = db.session.get(Replay, replay_id)
        if replay is None:
            raise ValueError("Replay not found")
        replay.status = "processing"
        db.session.commit()
        try:
            payload = json.loads(Path(replay.path).read_text(encoding="utf-8"))
            replay.metrics = analyze(payload, replay.player_slot)
            replay.status = "ready"
            replay.error = None
        except (ValueError, TypeError, OSError) as exc:
            replay.status = "failed"
            replay.metrics = None
            replay.error = str(exc)[:500]
        db.session.commit()
        return replay.status

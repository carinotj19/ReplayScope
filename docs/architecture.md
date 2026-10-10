# ReplayScope backend architecture

Flask receives and validates uploaded JSON. SQLAlchemy persists the replay, the experiment and the registered agent version. Replay bytes are stored on disk under a generated filename; SHA-256 deduplicates uploads within an experiment/version/player slot.

A committed replay can be processed inline (local development and tests) or dispatched to a Redis/RQ queue. The worker owns state transitions queued -> processing -> ready/failed.

Orbit Wars parsing is in a separate Python module, not in Flask route handlers. Its inputs are Kaggle steps[turn][player slot] observations. It counts ships held by planets and active fleets for each player, derives rank and win/loss/draw, and captures turn-level samples and production milestones.

Aggregations report Wilson intervals and sample sizes. Signals are descriptive: high-production planet loss and early production deficit are observable conditions, not proof of causation.

## Production gaps

This v0.1 backend is not yet production hardened. Before public deployment add authentication, authorization, migrations, object storage, replay retention, job retries and monitoring, request quotas and security auditing. Validate the parser against real exported replay examples before declaring format compatibility complete.

Do not pool 2P and 4P outcomes when judging strategic changes; use per-mode views.

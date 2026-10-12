"""Administrative recovery and the optional automatic stale-lease watchdog."""
import time

import click
from flask import current_app
from sqlalchemy import select

from .jobs import process_upload, _valid_until
from .models import ReplayUpload, UploadLease, db, utcnow


def _release(upload_id, *, force=False):
    """Reset only an expired, leased upload, or explicitly force a stuck one.

    The recovery path and committing worker both acquire the upload row first,
    followed by the lease row, preventing inconsistent lock ordering.
    """
    upload = db.session.execute(
        select(ReplayUpload).where(ReplayUpload.id == upload_id)
        .with_for_update().execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if upload is None or upload.status != "processing":
        db.session.rollback()
        return False
    lease = db.session.execute(
        select(UploadLease).where(UploadLease.upload_id == upload_id)
        .with_for_update().execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if not force:
        if lease is None or lease.token is None or _valid_until(lease.expires_at):
            db.session.rollback()
            return False
    upload.status = "queued"
    upload.error = None
    if lease is not None:
        lease.token = None  # immediately fence out the previous worker
        lease.expires_at = None
    db.session.commit()
    return True


def scan_stale_uploads(*, limit=20):
    """Recover expired leases once; suitable for cron or an external scheduler.

    An active lease is never reset. If a slow worker misses heartbeats and is
    reclaimed, its commit-time fencing check will reject its stale token.
    """
    candidates = db.session.execute(
        select(UploadLease.upload_id)
        .join(ReplayUpload, ReplayUpload.id == UploadLease.upload_id)
        .where(
            ReplayUpload.status == "processing",
            UploadLease.token.is_not(None),
            UploadLease.expires_at < utcnow(),
        )
        .order_by(UploadLease.expires_at)
        .limit(limit)
    ).scalars().all()
    db.session.rollback()
    recovered = 0
    for upload_id in candidates:
        if not _release(upload_id):
            continue
        result = process_upload(upload_id, current_app._get_current_object())
        if result == "ready":
            recovered += 1
    return len(candidates), recovered


def register_recovery_cli(app):
    @app.cli.command("recover-upload")
    @click.argument("upload_id")
    @click.option(
        "--force-stuck", is_flag=True,
        help="Reset a processing upload ONLY after confirming the original worker is stopped.",
    )
    def recover_upload(upload_id, force_stuck):
        """Retry failed work, or explicitly reset an abandoned processing state."""
        record = db.session.get(ReplayUpload, upload_id)
        if record is None:
            raise click.ClickException("Unknown upload ID")
        if record.status == "ready":
            click.echo("Already ready; no changes made.")
            return
        if record.status == "processing":
            if not force_stuck:
                raise click.ClickException(
                    "Upload is processing. Confirm its worker is STOPPED before --force-stuck."
                )
            db.session.rollback()
            if not _release(upload_id, force=True):
                raise click.ClickException("Upload status changed; try again.")
            click.echo("Invalidated existing lease; attempting recovery.")
        else:
            db.session.rollback()
            click.echo("Recovering failed or queued upload.")

        result = process_upload(upload_id, current_app._get_current_object())
        if result != "ready":
            raise click.ClickException(f"Upload status after attempt: {result}")
        click.echo(f"Upload {upload_id} recovered successfully.")

    @app.cli.command("sweep-stale")
    @click.option("--watch", is_flag=True, help="Keep checking until interrupted; run under process supervision.")
    @click.option("--interval", type=click.IntRange(5, 3600), default=30, show_default=True)
    @click.option("--limit", type=click.IntRange(1, 100), default=20, show_default=True)
    def sweep_stale(watch, interval, limit):
        """Safely reclaim expired worker leases without touching active uploads."""
        while True:
            seen, recovered = scan_stale_uploads(limit=limit)
            click.echo(f"Scanned {seen} expired upload(s); recovered {recovered}.")
            if not watch:
                break
            time.sleep(interval)

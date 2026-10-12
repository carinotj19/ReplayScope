"""Operator-initiated recovery for failed or stranded upload jobs."""
import click
from sqlalchemy import update
from flask import current_app

from .jobs import process_upload
from .models import ReplayUpload, db


def register_recovery_cli(app):
    @app.cli.command("recover-upload")
    @click.argument("upload_id")
    @click.option(
        "--force-stuck", is_flag=True,
        help="Reset a processing upload ONLY after confirming the original worker is stopped.",
    )
    def recover_upload(upload_id, force_stuck):
        """Reprocess a failed upload without creating duplicate benchmark runs.

        Use --force-stuck ONLY if an upload was stranded by a terminated worker.
        Never reset a running worker's in-progress upload.
        """
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
            result = db.session.execute(
                update(ReplayUpload)
                .where(
                    ReplayUpload.id == upload_id,
                    ReplayUpload.status == "processing",
                )
                .values(status="queued", error=None)
            )
            db.session.commit()
            if result.rowcount != 1:
                raise click.ClickException("Upload status changed; try again.")
            click.echo("Reset stranded processing state; attempting recovery.")
        else:
            click.echo(f"Recovering {record.status} upload.")

        result = process_upload(upload_id, current_app._get_current_object())
        if result != "ready":
            raise click.ClickException(f"Upload status after attempt: {result}")
        click.echo(f"Upload {upload_id} recovered successfully.")

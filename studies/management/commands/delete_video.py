from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models.deletion import Collector
from django.db.models.signals import pre_delete

from studies.models import Video, delete_video_on_s3
from studies.tasks import delete_video_from_cloud


class Command(BaseCommand):
    help = "Safely delete a Video from the database, and optionally trigger immediate S3 deletion rather than waiting 7 days."

    def add_arguments(self, parser):
        parser.add_argument("--uuid", type=str, help="UUID of the Video.")
        parser.add_argument("--full-name", type=str, help="Full name of the Video.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview deletion without deleting.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Actually perform deletion.",
        )
        parser.add_argument(
            "--immediate-s3",
            action="store_true",
            help="Delete from S3 immediately instead of waiting 7 days.",
        )

    def handle(self, *args, **options):
        uuid = options.get("uuid")
        full_name = options.get("full_name")
        dry_run = options.get("dry_run")
        force = options.get("force")
        immediate_s3 = options.get("immediate_s3")

        if not uuid and not full_name:
            raise CommandError("Provide either --uuid or --full-name.")

        if not dry_run and not force:
            raise CommandError(
                "Refusing to delete without --force. Use --dry-run to preview."
            )

        # Find the video
        try:
            if uuid:
                video = Video.objects.get(uuid=uuid)
            else:
                video = Video.objects.get(full_name=full_name)
        except Video.DoesNotExist:
            raise CommandError("Video not found.")
        except Video.MultipleObjectsReturned:
            raise CommandError("Multiple matches found. Use UUID.")

        self.stdout.write(self.style.WARNING("\nVideo found:"))
        self.stdout.write(f"  ID: {video.id}")
        self.stdout.write(f"  UUID: {video.uuid}")
        self.stdout.write(f"  Full name: {video.full_name}")

        # Check for cascading deletions due to related objects
        collector = Collector(using="default")
        collector.collect([video])

        related_counts = defaultdict(int)
        for model, objs in collector.data.items():
            related_counts[model._meta.label] += len(objs)

        self.stdout.write(self.style.WARNING("\nObjects that will be deleted:"))
        total = 0
        for model_label, count in sorted(related_counts.items()):
            self.stdout.write(f"  {model_label}: {count}")
            total += count

        self.stdout.write(f"\n  TOTAL objects deleted: {total}")

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS("\nDry run complete. No deletion performed.")
            )
            return

        # Perform deletion
        with transaction.atomic():
            if immediate_s3:
                self.stdout.write(
                    self.style.WARNING("\nTriggering immediate S3 deletion...")
                )
                # Disconnect pre_delete signal temporarily to avoid scheduling delayed S3 deletion task
                pre_delete.disconnect(
                    receiver=delete_video_on_s3,
                    sender=Video,
                )
                try:
                    # Trigger immediate S3 deletion
                    delete_video_from_cloud.apply_async(
                        args=(
                            video.full_name,
                            video.recording_method_is_pipe,
                            video.study_type_is_jspsych,
                        ),
                        queue="cleanup",
                    )
                    # Delete without triggering delayed signal
                    video.delete()
                finally:
                    # Reconnect the signal
                    pre_delete.connect(
                        receiver=delete_video_on_s3,
                        sender=Video,
                    )
            else:
                video.delete()

        self.stdout.write(self.style.SUCCESS("\nVideo deleted successfully."))

        if immediate_s3:
            self.stdout.write(self.style.SUCCESS("S3 deletion triggered immediately."))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "S3 deletion scheduled via pre_delete signal (7-day delay)."
                )
            )

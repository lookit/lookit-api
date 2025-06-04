import csv
from unittest.mock import MagicMock, patch

from django.core.management.base import BaseCommand

from studies.models import Video


class Command(BaseCommand):
    help = "Move info about Pipe recordings into our database from the exported recordings CSV file, without running any S3 actions. This command is meant to be used for Pipe webhook failures that occurred after the S3 file renaming step. WARNING: this command does NOT check whether the new filename exists in the appropriate S3 bucket, which means it is possible to add an invalid video object/filename using this command. This command does check that the associated study and response objects (UUIDs taken from the new filenames) exist in the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "csv_file",
            type=str,
            help="Path to CSV file with exported Pipe recording data",
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Try processing the CSV file and print the logs, without adding any objects to the database.",
        )

    def handle(self, *args, **options):
        path = options["csv_file"]
        dry_run = options["dry_run"]

        with patch("studies.models.S3_RESOURCE.Object") as mock_s3_object:
            # We need to mock the S3 object and return values for copy_from/delete so that this part of the Pipe webhook processing is skipped and does not throw errors when the old Pipe file cannot be found (because it has already been renamed).
            mock_obj = MagicMock()
            mock_obj.copy_from.return_value = None
            mock_obj.delete.return_value = None
            mock_s3_object.return_value = mock_obj

            log_prefix = "[DRY RUN] " if dry_run else ""

            with open(path, newline="", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    if (
                        not row.get("payload")
                        or not row.get("name")
                        or not row.get("id")
                    ):
                        self.stderr.write(
                            self.style.WARNING(
                                f"{log_prefix}Skipping invalid row: {row}"
                            )
                        )
                        continue

                    try:
                        # mimic the format of data that comes in via the Pipe webhook POST to pass to Video.from_pipe_payload
                        payload = {
                            "data": {
                                "id": int(row["id"]),
                                "videoName": row["name"],
                                "type": "MP4",
                                "payload": row["payload"],
                            }
                        }

                        full_name = f"{payload['data']['payload']}.{payload['data']['type'].lower()}"

                        # Log and skip any videos that already exist in the database
                        if Video.objects.filter(full_name=full_name).exists():
                            self.stdout.write(
                                f"{log_prefix}Skipped existing video: {full_name}"
                            )
                            continue

                        if not dry_run:
                            Video.from_pipe_payload(payload)

                        self.stdout.write(
                            self.style.SUCCESS(
                                f"{log_prefix}Created video: {full_name}"
                            )
                        )

                    except Exception as e:
                        self.stderr.write(
                            self.style.ERROR(
                                f"{log_prefix}Failed to process row {row.get('id', '')}: {e}"
                            )
                        )

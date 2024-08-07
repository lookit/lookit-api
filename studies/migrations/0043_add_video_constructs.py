# -*- coding: utf-8 -*-
# Generated by Django 1.11.5 on 2019-02-20 17:07
from __future__ import unicode_literals

import logging
import uuid

import boto3
import dateutil
import django.db.models.deletion
import fleep
from botocore.exceptions import ClientError
from django.conf import settings
from django.db import migrations, models

S3_RESOURCE = boto3.resource("s3")
VALID_CONSENT_FRAMES = ("1-video-consent",)

logger = logging.getLogger(__name__)
date_parser = dateutil.parser


def generate_videos_from_responses(apps, schema_editor):
    """Custom migration code to generate videos from responses."""
    ResponseModel = apps.get_model("studies", "Response")
    VideoModel = apps.get_model("studies", "Video")
    ConsentRulingModel = apps.get_model("studies", "ConsentRuling")
    UserModel = apps.get_model("accounts", "User")
    consent_admin = UserModel.objects.filter(
        username="lookit-consent-manager@mit.edu"
    ).first()
    for response in ResponseModel.objects.all():
        generate_videos_from_events(response, VideoModel)
        apply_initial_consent_ruling(response, ConsentRulingModel, consent_admin)


def apply_initial_consent_ruling(response, consent_ruling_model, consent_admin):
    """

    :param response: a Response object
    :param consent_ruling_model: the ConsentRuling model
    :param consent_admin: User model for consent administrator
    """
    ConsentRuling = consent_ruling_model

    ConsentRuling.objects.create(
        action="accepted",
        arbiter=consent_admin,
        response=response,
        comments="Automatically accepted and may not be verified; recorded before consent manager deployed.",
    )


def generate_videos_from_events(response, video_model):
    """Creates the video containers/representations for this given response.

    We should only really invoke this as part of a migration as of right now (2/8/2019),
    but it's quite possible we'll have the need for dynamic upsertion later.
    """

    seen_ids = set()
    video_objects = []
    Video = video_model

    # Using a constructive approach here, but with an ancillary seen_ids list b/c Django models without
    # primary keys are unhashable for some dumb reason (even though they have unique fields...)
    for frame_id, event_data in response.exp_data.items():
        if event_data.get("videoList", None) and event_data.get("videoId", None):
            # We've officially captured video here!
            events = event_data.get("eventTimings", [])
            for event in events:
                video_id = event["videoId"]
                pipe_name = event["pipeId"]  # what we call "ID" they call "name"
                stream_time = event["streamTime"]
                if (
                    video_id not in seen_ids
                    and pipe_name
                    and stream_time
                    and stream_time > 0
                ):
                    # Try looking for the regular ID first.
                    file_obj = S3_RESOURCE.Object(
                        settings.BUCKET_NAME, f"{video_id}.mp4"
                    )
                    try:
                        s3_response = file_obj.get()
                    except ClientError:
                        try:  # If that doesn't work, use the pipe name.
                            file_obj = S3_RESOURCE.Object(
                                settings.BUCKET_NAME, f"{pipe_name}.mp4"
                            )
                            s3_response = file_obj.get()
                        except ClientError:
                            logger.warning(
                                f"could not find {video_id} or {pipe_name} in S3!"
                            )
                            continue
                    # Read first 32 bytes from streaming body (file header) to get actual filetype.
                    streaming_body = s3_response["Body"]
                    file_header_buffer: bytes = streaming_body.read(32)
                    file_info = fleep.get(file_header_buffer)
                    streaming_body.close()

                    video_objects.append(
                        Video(
                            pipe_name=pipe_name,
                            created_at=date_parser.parse(event["timestamp"]),
                            date_modified=s3_response["LastModified"],
                            #  Can't get the *actual* pipe id property, it's in the webhook payload...
                            frame_id=frame_id,
                            full_name=f"{video_id}.{file_info.extension[0]}",
                            study=response.study,
                            response=response,
                            is_consent_footage=frame_id in VALID_CONSENT_FRAMES,
                        )
                    )
                    seen_ids.add(video_id)

    return Video.objects.bulk_create(video_objects)


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("studies", "0042_add_consent_flag_to_response"),
    ]

    operations = [
        migrations.CreateModel(
            name="ConsentRuling",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "uuid",
                    models.UUIDField(db_index=True, default=uuid.uuid4, unique=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "action",
                    models.CharField(
                        choices=[("accepted", "rejected", "pending")],
                        db_index=True,
                        max_length=100,
                    ),
                ),
                ("comments", models.TextField(null=True)),
                (
                    "arbiter",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="consent_rulings",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Video",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "uuid",
                    models.UUIDField(db_index=True, default=uuid.uuid4, unique=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("date_modified", models.DateTimeField(auto_now=True)),
                ("pipe_name", models.CharField(max_length=255, unique=True)),
                ("pipe_numeric_id", models.IntegerField(null=True)),
                ("frame_id", models.CharField(max_length=255)),
                ("size", models.PositiveIntegerField(null=True)),
                (
                    "full_name",
                    models.CharField(db_index=True, max_length=255, unique=True),
                ),
                (
                    "is_consent_footage",
                    models.BooleanField(db_index=True, default=False),
                ),
            ],
        ),
        migrations.AddField(
            model_name="video",
            name="response",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="videos",
                to="studies.Response",
            ),
        ),
        migrations.AddField(
            model_name="video",
            name="study",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="videos",
                to="studies.Study",
            ),
        ),
        migrations.AddField(
            model_name="consentruling",
            name="response",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="consent_rulings",
                to="studies.Response",
            ),
        ),
        migrations.AlterIndexTogether(
            name="consentruling",
            index_together=set([("response", "action"), ("response", "arbiter")]),
        ),
        # Finally, run custom migration code
        migrations.RunPython(
            generate_videos_from_responses, reverse_code=migrations.RunPython.noop
        ),
    ]

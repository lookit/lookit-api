# -*- coding: utf-8 -*-
# Generated by Django 1.11.21 on 2019-08-09 17:29
from __future__ import unicode_literals

from datetime import datetime, timezone

import django.utils.timezone
from django.db import migrations, models


def add_s3_timestamp(apps, schema_editor):
    """Custom migration code to generate videos from responses."""
    VideoModel = apps.get_model("studies", "Video")
    for video in VideoModel.objects.all():
        _, study_uuid, frame_id, response_uuid, timestamp, _ = video.full_name.split(
            "_"
        )
        video.s3_timestamp = datetime.fromtimestamp(int(timestamp) / 1000, timezone.utc)
        video.save()


class Migration(migrations.Migration):
    dependencies = [("studies", "0051_eligibility_criteria_expression_support")]

    operations = [
        migrations.RemoveField(model_name="video", name="date_modified"),
        migrations.AddField(
            model_name="video",
            name="s3_timestamp",
            field=models.DateTimeField(default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.RunPython(add_s3_timestamp, reverse_code=migrations.RunPython.noop),
    ]

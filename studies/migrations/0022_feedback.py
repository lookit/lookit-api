# -*- coding: utf-8 -*-
# Generated by Django 1.11.2 on 2017-08-17 13:36
from __future__ import unicode_literals

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("studies", "0021_auto_20170809_1719"),
    ]

    operations = [
        migrations.CreateModel(
            name="Feedback",
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
                ("comment", models.TextField()),
                (
                    "researcher",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "response",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to="studies.Response",
                    ),
                ),
            ],
            options={"permissions": (("can_view_feedback", "Can View Feedback"),)},
        )
    ]

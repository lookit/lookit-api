# -*- coding: utf-8 -*-
# Generated by Django 1.11.5 on 2019-01-23 23:46
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("studies", "0041_add_built_field")]

    operations = [
        migrations.AddField(
            model_name="response",
            name="completed_consent_frame",
            field=models.BooleanField(default=False),
        ),
        migrations.RunSQL("UPDATE studies_response SET completed_consent_frame=TRUE;"),
    ]

# -*- coding: utf-8 -*-
# Generated by Django 1.11.2 on 2017-11-07 22:28
from __future__ import unicode_literals

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("studies", "0036_add_scheduled_jobs")]

    operations = [
        migrations.AddField(
            model_name="response",
            name="date_created",
            field=models.DateTimeField(
                auto_now_add=True, default=django.utils.timezone.now
            ),
            preserve_default=False,
        )
    ]

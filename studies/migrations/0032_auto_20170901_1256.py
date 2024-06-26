# -*- coding: utf-8 -*-
# Generated by Django 1.11.2 on 2017-09-01 16:56
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("studies", "0031_merge_20170828_1227")]

    operations = [
        migrations.RemoveField(model_name="study", name="max_age"),
        migrations.RemoveField(model_name="study", name="min_age"),
        migrations.AddField(
            model_name="study",
            name="max_age_months",
            field=models.IntegerField(default=0, null=True),
        ),
        migrations.AddField(
            model_name="study",
            name="max_age_years",
            field=models.IntegerField(default=0, null=True),
        ),
        migrations.AddField(
            model_name="study",
            name="min_age_months",
            field=models.IntegerField(default=0, null=True),
        ),
        migrations.AddField(
            model_name="study",
            name="min_age_years",
            field=models.IntegerField(default=0, null=True),
        ),
    ]

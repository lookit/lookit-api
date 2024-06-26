# -*- coding: utf-8 -*-
# Generated by Django 1.11.2 on 2017-07-18 21:14
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0011_merge_20170710_1820")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="email_new_studies",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="user",
            name="email_next_session",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="user",
            name="email_opt_out",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="email_results_published",
            field=models.BooleanField(default=True),
        ),
    ]

# -*- coding: utf-8 -*-
# Generated by Django 1.11.2 on 2017-09-07 19:19
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0028_auto_20170825_1532")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="former_lookit_id",
            field=models.CharField(blank=True, max_length=255),
        )
    ]

# -*- coding: utf-8 -*-
# Generated by Django 1.11.2 on 2017-06-28 17:49
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("studies", "0004_auto_20170616_0244")]

    operations = [
        migrations.AddField(
            model_name="study",
            name="last_known_addons_sha",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="study",
            name="last_known_player_sha",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="study",
            name="remote_folder_url",
            field=models.URLField(blank=True),
        ),
    ]

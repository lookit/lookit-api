# -*- coding: utf-8 -*-
# Generated by Django 1.11.2 on 2017-08-25 18:22
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("studies", "0027_auto_20170818_1551")]

    operations = [
        migrations.AddField(
            model_name="study", name="preview_url", field=models.URLField(blank=True)
        )
    ]

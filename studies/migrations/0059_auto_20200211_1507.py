# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2020-02-11 20:07
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('studies', '0058_study_hash_digits'),
    ]

    operations = [
        migrations.AddField(
            model_name='study',
            name='is_building',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='study',
            name='is_previewing',
            field=models.BooleanField(default=False),
        ),
    ]

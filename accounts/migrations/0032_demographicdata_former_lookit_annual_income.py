# -*- coding: utf-8 -*-
# Generated by Django 1.11.2 on 2017-09-08 04:53
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0031_auto_20170908_0009")]

    operations = [
        migrations.AddField(
            model_name="demographicdata",
            name="former_lookit_annual_income",
            field=models.CharField(blank=True, max_length=30),
        )
    ]

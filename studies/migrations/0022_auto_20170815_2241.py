# -*- coding: utf-8 -*-
# Generated by Django 1.11.2 on 2017-08-15 22:41
from __future__ import unicode_literals

from django.db import migrations
import project.fields.datetime_aware_jsonfield


class Migration(migrations.Migration):

    dependencies = [("studies", "0021_auto_20170809_1719")]

    operations = [
        migrations.AddField(
            model_name="responselog",
            name="extra",
            field=project.fields.datetime_aware_jsonfield.DateTimeAwareJSONField(
                null=True
            ),
        ),
        migrations.AddField(
            model_name="studylog",
            name="extra",
            field=project.fields.datetime_aware_jsonfield.DateTimeAwareJSONField(
                null=True
            ),
        ),
    ]

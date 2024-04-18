# -*- coding: utf-8 -*-
# Generated by Django 1.11.2 on 2018-02-19 17:59
from __future__ import unicode_literals

from django.db import migrations

import project.fields.datetime_aware_jsonfield


class Migration(migrations.Migration):
    dependencies = [("studies", "0038_auto_20171109_1749")]

    operations = [
        migrations.AlterField(
            model_name="studytype",
            name="configuration",
            field=project.fields.datetime_aware_jsonfield.DateTimeAwareJSONField(
                default={
                    "metadata": {
                        "fields": {
                            "addons_repo_url": "https://github.com/lookit/exp-addons",
                            "last_known_addons_sha": None,
                            "last_known_player_sha": None,
                        }
                    },
                    "task_module": "studies.tasks",
                }
            ),
        )
    ]

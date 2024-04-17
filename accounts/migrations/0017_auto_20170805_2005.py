# -*- coding: utf-8 -*-
# Generated by Django 1.11.2 on 2017-08-05 20:05
from __future__ import unicode_literals

import multiselectfield.db.fields
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("accounts", "0016_auto_20170805_1855")]

    operations = [
        migrations.AlterField(
            model_name="demographicdata",
            name="race_identification",
            field=multiselectfield.db.fields.MultiSelectField(
                choices=[
                    ("white", "White"),
                    ("hisp", "Hispanic, Latino, or Spanish origin"),
                    ("black", "Black or African American"),
                    ("asian", "Asian"),
                    ("native", "American Indian or Alaska Native"),
                    ("mideast-naf", "Middle Eastern or North African"),
                    ("hawaiian-pac-isl", "Native Hawaiian or Other Pacific Islander"),
                    ("other", "Another race, ethnicity, or origin"),
                ],
                max_length=64,
            ),
        )
    ]

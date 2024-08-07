# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-08-21 16:39
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0042_make_bitfield_migrations_easier")]

    operations = [
        migrations.AlterField(
            model_name="child",
            name="gestational_age_at_birth",
            field=models.PositiveSmallIntegerField(
                blank=True,
                choices=[
                    (None, "Not sure or prefer not to answer"),
                    (0, "Under 24 weeks"),
                    (1, "24 weeks"),
                    (2, "25 weeks"),
                    (3, "26 weeks"),
                    (4, "27 weeks"),
                    (5, "28 weeks"),
                    (6, "29 weeks"),
                    (7, "30 weeks"),
                    (8, "31 weeks"),
                    (9, "32 weeks"),
                    (10, "33 weeks"),
                    (11, "34 weeks"),
                    (12, "35 weeks"),
                    (13, "36 weeks"),
                    (14, "37 weeks"),
                    (15, "38 weeks"),
                    (16, "39 weeks"),
                    (17, "40 or more weeks"),
                ],
                default=None,
                null=True,
            ),
        )
    ]

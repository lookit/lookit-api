# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-08-19 19:52
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("studies", "0052_add-s3-timestamp")]

    operations = [
        migrations.RemoveField(
            model_name="eligibleparticipantquerymodel", name="study"
        ),
        migrations.DeleteModel(name="EligibleParticipantQueryModel"),
    ]

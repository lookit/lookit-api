# -*- coding: utf-8 -*-
# Generated by Django 1.11.2 on 2017-11-16 15:51
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("accounts", "0037_auto_20171115_1143")]

    operations = [
        migrations.RemoveField(model_name="demographicdata", name="date_created")
    ]

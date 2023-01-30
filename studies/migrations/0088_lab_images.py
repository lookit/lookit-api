# Generated by Django 3.2.11 on 2023-01-19 20:47

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0054_update_demo_fields"),
        ("studies", "0087_study_priority"),
    ]

    operations = [
        migrations.AddField(
            model_name="lab",
            name="badge",
            field=models.ImageField(blank=True, null=True, upload_to="lab_images/"),
        ),
        migrations.AddField(
            model_name="lab",
            name="banner",
            field=models.ImageField(blank=True, null=True, upload_to="lab_images/"),
        ),
        migrations.AlterField(
            model_name="response",
            name="child",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="responses",
                to="accounts.child",
            ),
        ),
    ]

# Generated by Django 3.2.11 on 2022-08-03 16:57

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("studies", "0082_remove_response_log"),
    ]

    operations = [
        migrations.AddField(
            model_name="study",
            name="comments_extra",
            field=models.JSONField(blank=True, null=True),
        ),
    ]

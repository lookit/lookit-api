# Generated by Django 3.2.25 on 2024-10-15 22:02

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("studies", "0098_add_scheduled_video_upload_cleanup"),
    ]

    operations = [
        migrations.AlterField(
            model_name="response",
            name="recording_method",
            field=models.CharField(max_length=50, null=True),
        ),
    ]

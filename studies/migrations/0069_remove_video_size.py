# Generated by Django 3.0.14 on 2021-05-18 11:03

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("studies", "0068_add_scheduled_docker_cleanup"),
    ]

    operations = [
        migrations.RemoveField(model_name="video", name="size"),
    ]

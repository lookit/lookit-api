# -*- coding: utf-8 -*-
# Generated by Django 1.11.2 on 2018-07-06 19:33
from __future__ import unicode_literals

from django.db import migrations

three_am_crontab_schedule_dict = dict(
    minute="0", hour="3", day_of_week="*", day_of_month="*", month_of_year="*"
)
cleanup_docker_images_periodic_task_dict = dict(
    name="Nightly docker image cleanup", task="studies.tasks.cleanup_docker_images"
)


def create_scheduled_jobs(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    three_am_crontab_schedule, created = CrontabSchedule.objects.get_or_create(
        **three_am_crontab_schedule_dict
    )
    cleanup_docker_images_periodic_task_dict.update(
        dict(crontab=three_am_crontab_schedule)
    )
    cleanup_docker_images_periodic_task, created = PeriodicTask.objects.get_or_create(
        **cleanup_docker_images_periodic_task_dict
    )


class Migration(migrations.Migration):
    dependencies = [("studies", "0039_auto_20180219_1259")]

    operations = [migrations.RunPython(create_scheduled_jobs)]

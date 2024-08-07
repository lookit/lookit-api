# Generated by Django 3.2.11 on 2022-08-30 14:56

from django.db import migrations, models


def forwards_func(apps, schema_editor):
    study_model = apps.get_model("studies", "Study")
    for study in study_model.objects.filter(comments_extra__isnull=True):
        study.comments_extra = {}
        study.save()


def reverse_func(apps, schema_editor):
    # On reverse the default will be removed, there is nothing that needs to be undone here.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("studies", "0084_study_status_change_date"),
    ]

    operations = [
        migrations.AlterField(
            model_name="study",
            name="comments_extra",
            field=models.JSONField(blank=True, default=dict, null=True),
        ),
        migrations.RunPython(forwards_func, reverse_code=reverse_func),
    ]

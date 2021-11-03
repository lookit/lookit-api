# Generated by Django 3.0.14 on 2021-10-26 17:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("studies", "0077_add_fields_to_external_study_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="study",
            name="exit_url",
            field=models.URLField(default="https://lookit.mit.edu/studies/history/"),
        ),
    ]
# Generated by Django 3.2.11 on 2023-12-07 05:59

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("studies", "0095_add_jspsych_studytype"),
    ]

    operations = [
        migrations.AddField(
            model_name="response",
            name="survey_consent",
            field=models.BooleanField(default=False),
        ),
    ]

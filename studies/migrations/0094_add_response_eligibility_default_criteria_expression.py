# Generated by Django 3.2.11 on 2023-11-08 05:47

import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("studies", "0093_remove_studytype_configuration"),
    ]

    operations = [
        migrations.AddField(
            model_name="response",
            name="eligibility",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(
                    choices=[
                        ("Eligible", "Eligible"),
                        ("Ineligible_TooYoung", "Ineligible Young"),
                        ("Ineligible_TooOld", "Ineligible Old"),
                        ("Ineligible_CriteriaExpression", "Ineligible Criteria"),
                        ("Ineligible_Participation", "Ineligible Participation"),
                    ],
                    max_length=100,
                ),
                blank=True,
                default=list,
                size=None,
            ),
        ),
        migrations.AlterField(
            model_name="study",
            name="criteria_expression",
            field=models.TextField(blank=True, default=""),
        ),
    ]
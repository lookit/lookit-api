# Generated by Django 3.2.11 on 2022-07-14 14:04

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0053_update_jsonfield"),
    ]

    operations = [
        migrations.RenameField(
            model_name="demographicdata",
            old_name="number_of_guardians_explanation",
            new_name="guardians_explanation",
        ),
        migrations.RenameField(
            model_name="demographicdata",
            old_name="languages_spoken_at_home",
            new_name="old_languages_spoken_at_home",
        ),
        migrations.RenameField(
            model_name="demographicdata",
            old_name="number_of_books",
            new_name="old_number_of_books",
        ),
        migrations.RenameField(
            model_name="demographicdata",
            old_name="spouse_education_level",
            new_name="old_spouse_education_level",
        ),
        migrations.RenameField(
            model_name="demographicdata",
            old_name="race_identification",
            new_name="us_race_ethnicity_identification",
        ),
        migrations.AddField(
            model_name="child",
            name="gender_self_describe",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="demographicdata",
            name="gender_self_describe",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="demographicdata",
            name="us_race_ethnicity_identification_describe",
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name="child",
            name="gender",
            field=models.CharField(
                choices=[
                    ("m", "male"),
                    ("f", "female"),
                    ("o", "open response"),
                    ("na", "prefer not to answer"),
                ],
                max_length=2,
            ),
        ),
        migrations.AlterField(
            model_name="demographicdata",
            name="gender",
            field=models.CharField(
                blank=True,
                choices=[
                    ("m", "male"),
                    ("f", "female"),
                    ("o", "open response"),
                    ("na", "prefer not to answer"),
                ],
                max_length=2,
            ),
        ),
        migrations.AlterField(
            model_name="demographicdata",
            name="number_of_guardians",
            field=models.CharField(
                blank=True,
                choices=[
                    ("1", "1"),
                    ("2", "2"),
                    ("3", "3"),
                    ("varies", "Another number, or explain below"),
                ],
                max_length=6,
            ),
        ),
    ]

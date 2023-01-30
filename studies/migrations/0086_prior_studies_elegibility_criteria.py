# Generated by Django 3.2.11 on 2022-12-06 16:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("studies", "0085_study_comments_extra_set_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="study",
            name="must_have_participated",
            field=models.ManyToManyField(
                blank=True, related_name="expected_participation", to="studies.Study"
            ),
        ),
        migrations.AddField(
            model_name="study",
            name="must_not_have_participated",
            field=models.ManyToManyField(
                blank=True, related_name="expected_nonparticipation", to="studies.Study"
            ),
        ),
    ]

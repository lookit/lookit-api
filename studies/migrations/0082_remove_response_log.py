# Generated by Django 3.2.11 on 2022-07-26 12:58

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("studies", "0081_lab_slug"),
    ]

    operations = [
        migrations.DeleteModel(
            name="ResponseLog",
        ),
    ]

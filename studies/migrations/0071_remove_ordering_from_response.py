# Generated by Django 3.0.14 on 2021-06-29 18:34

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("studies", "0070_auto_20210521_0632"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="response",
            options={
                "base_manager_name": "related_manager",
                "permissions": (
                    (
                        "view_all_response_data_in_analytics",
                        "View all response data in analytics",
                    ),
                ),
            },
        ),
    ]

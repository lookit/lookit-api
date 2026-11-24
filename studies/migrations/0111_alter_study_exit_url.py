from django.db import migrations, models

import studies.models


class Migration(migrations.Migration):
    dependencies = [
        ("studies", "0110_study_query_param_names"),
    ]

    operations = [
        migrations.AlterField(
            model_name="study",
            name="exit_url",
            field=models.URLField(
                blank=True, default=studies.models.default_exit_url, null=True
            ),
        ),
    ]

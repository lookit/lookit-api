from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("studies", "0106_add_researcher_valid_response"),
    ]

    operations = [
        migrations.AddField(
            model_name="lab",
            name="created_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

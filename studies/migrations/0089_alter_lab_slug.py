# Generated by Django 3.2.11 on 2023-04-02 21:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("studies", "0088_lab_images"),
    ]

    operations = [
        migrations.AlterField(
            model_name="lab",
            name="slug",
            field=models.SlugField(
                default=None,
                help_text='A unique URL ending (slug) for the webpage that will show any discoverable, active studies for this lab. For example, entering "my-lab-name" in this box will produce the custom URL "https://lookit.mit.edu/studies/my-lab-name" for this lab. Slugs should not contain spaces and can contain letters, numbers, underscores, and/or hyphens.',
                max_length=255,
                null=True,
                unique=True,
                verbose_name="Custom URL Slug",
            ),
        ),
    ]

from django.db import migrations, models

JSPSYCH_PLUGINS = [
    {
        "name": "Fullscreen",
        "url": "https://unpkg.com/@jspsych/plugin-fullscreen@2.1.0",
        "integrity": "sha384-JQEV9wMXFDbTpp1eYJSU9G7uQeyZcLGabno5ZHQJGytUBG19mTZ+ZBV5dsm7m6Mf",
        "category": "jspsych",
    },
    {
        "name": "HTML Button Response",
        "url": "https://unpkg.com/@jspsych/plugin-html-button-response@2.0.0",
        "integrity": "sha384-YkXp8JHPul+fAB8ACoBIXD4fMzweAXqwajNbmkFxKo0z4CEZJssZ5EWqMCefJs8J",
        "category": "jspsych",
    },
    {
        "name": "HTML Keyboard Response",
        "url": "https://unpkg.com/@jspsych/plugin-html-keyboard-response@2.0.0",
        "integrity": "sha384-3rxt+0Ug6ruPv/HON9dlEFlhrBHhqZeHQizgSO59PsPIu0OGscC8sMgifOe7/uJG",
        "category": "jspsych",
    },
    {
        "name": "Image Button Response",
        "url": "https://unpkg.com/@jspsych/plugin-image-button-response@2.0.0",
        "integrity": "sha384-akngF9Va8sW0TdFvi4EsfM6SGOE94o2XZ+n99/QKYbVhdUEvX1h/OJdfa8yRoEPX",
        "category": "jspsych",
    },
    {
        "name": "Image Hotspots (contrib)",
        "url": "https://unpkg.com/@jspsych-contrib/plugin-image-hotspots@1.1.0",
        "integrity": "sha384-7AhLUtRbC1B+Xy/IvMrbPwOq6HljuZNa73fxtKSPix5U/fRpljnK/hkcJGtKsTRJ",
        "category": "jspsych-contrib",
    },
    {
        "name": "Image Keyboard Response",
        "url": "https://unpkg.com/@jspsych/plugin-image-keyboard-response@2.0.0",
        "integrity": "sha384-BqelFj5L0Q3ifJf9rlngrTf8zZgfZhmaGwODK7vjHchtxS/Um3LVYj58qymHDn1i",
        "category": "jspsych",
    },
    {
        "name": "Preload",
        "url": "https://unpkg.com/@jspsych/plugin-preload@2.0.0",
        "integrity": "sha384-veBuhHbf5WLQIFlG9N6a+5E/kRYJcBTDKkqJRTkc7wuGwptljsBa2fYuTseMkOBI",
        "category": "jspsych",
    },
    {
        "name": "Survey Likert",
        "url": "https://unpkg.com/@jspsych/plugin-survey-likert@2.2.0",
        "integrity": "sha384-88dibDOm9kxaXAwTWWQWZa1+0RBPA6WNU0lrWYLfeMEIQgovura7DxPG9kPXrBRc",
        "category": "jspsych",
    },
    {
        "name": "Survey Multi-Choice",
        "url": "https://unpkg.com/@jspsych/plugin-survey-multi-choice@2.1.0",
        "integrity": "sha384-NDx/PP6brJOK2yI3xA9yYbsgRe6I7BUZ3jcBD9aiVRWNYiei88wLmzsMEdWGJXOr",
        "category": "jspsych",
    },
    {
        "name": "Survey Text",
        "url": "https://unpkg.com/@jspsych/plugin-survey-text@2.1.0",
        "integrity": "sha384-wSdh5i8tkmhhMiddYPH0Sc0HNw6wDfVWT80sTyRdjs62ctEKZHPLDdF2WXj2sPa/",
        "category": "jspsych",
    },
    {
        "name": "Tangram Game (contrib)",
        "url": "https://unpkg.com/@jspsych-contrib/plugin-tangram-game",
        "integrity": "sha384-baK1nai9zI/Ela9b8M1rPHE2echlvpfCWpE8f1FALUSteEUwYRA77m3nGKaV/IyZ",
        "category": "jspsych-contrib",
    },
    {
        "name": "Video Button Response",
        "url": "https://unpkg.com/@jspsych/plugin-video-button-response@2.0.0",
        "integrity": "sha384-u1N4HtXTAx8IPaZxRLKurCoPhFnSQ+TrF+33Lr1ORBhnRogBnU8Fd7tbPkFh1uUj",
        "category": "jspsych",
    },
    {
        "name": "Video Hotspots (contrib)",
        "url": "https://unpkg.com/@jspsych-contrib/plugin-video-hotspots@1.1.0",
        "integrity": "sha384-us3mQaYVUiroiiS/C+w4pJnlRl7E65KWAPC/zqIXWJxpHQhXfn06a2C+fxhkVLbd",
        "category": "jspsych-contrib",
    },
    {
        "name": "Video Keyboard Response",
        "url": "https://unpkg.com/@jspsych/plugin-video-keyboard-response@2.1.0",
        "integrity": "sha384-a/hZpVf76Sh4k+Do3dVTBltuX/XuRfZnokDUg7Qsw5J+pMy00lzyMX5EovruBI3M",
        "category": "jspsych",
    },
]


def seed_plugins_and_assign_to_existing_studies(apps, schema_editor):
    jspsych_plugin = apps.get_model("studies", "JSPsychPlugin")
    study = apps.get_model("studies", "Study")
    study_type = apps.get_model("studies", "StudyType")

    plugins = [jspsych_plugin.objects.create(**data) for data in JSPSYCH_PLUGINS]

    jspsych_type = study_type.objects.filter(name="jsPsych").first()
    if jspsych_type:
        for s in study.objects.filter(study_type=jspsych_type):
            s.jspsych_plugins.set(plugins)


class Migration(migrations.Migration):
    dependencies = [
        ("studies", "0107_add_lab_created_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="JSPsychPlugin",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("url", models.URLField(max_length=500)),
                ("integrity", models.CharField(max_length=255)),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("jspsych", "Core jsPsych"),
                            ("jspsych-contrib", "jsPsych-contrib"),
                            ("chs-jspsych", "CHS jsPsych"),
                        ],
                        max_length=20,
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="study",
            name="jspsych_plugins",
            field=models.ManyToManyField(
                blank=True,
                related_name="studies",
                to="studies.jspsychplugin",
            ),
        ),
        migrations.RunPython(
            seed_plugins_and_assign_to_existing_studies,
            migrations.RunPython.noop,
        ),
    ]

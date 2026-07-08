from django.db import migrations, models

JSPSYCH_LIBRARY = [
    {
        "name": "jsPsych CSS",
        "url": "https://unpkg.com/jspsych@8.0.3/css/jspsych.css",
        "integrity": "sha384-JNNpz6XWsC9uPPHlCuf9rr6LrSD2uYvbkApP5kAp6g/lFBue51K1kMzxGawS50nK",
        "category": "jspsych-library",
        "file_type": "css",
        "order": 1,
    },
    {
        "name": "jsPsych",
        "url": "https://unpkg.com/jspsych@8.0.3",
        "integrity": "sha384-YlD0H7IvUJqPzueP9WYLT0zKLtEnoNlbxZ5Kd4jg+3orRU5jXGk4ozBUMLqQ+SQ1",
        "category": "jspsych-library",
        "file_type": "js",
        "order": 2,
    },
]

CHS_JSPSYCH_PLUGINS = [
    {
        "name": "CHS Style",
        "url": "https://unpkg.com/@lookit/style@0.4.0",
        "integrity": "sha384-e+HIPVgafegNi8YhAiKPvYDv1K+hihQ2g4qd/ZYHPtTBJyfTEDcfDLYyfDdk1lI/",
        "category": "chs-jspsych",
        "file_type": "css",
        "order": 1,
    },
    {
        "name": "CHS Data",
        "url": "https://unpkg.com/@lookit/data@0.3.0",
        "integrity": "sha384-kpjDWFQo7CQk9i6Bq58NNCC8i5mFCMAbapMhF3xxLmEc2vD6wHqMc/aI0w1u/fTh",
        "category": "chs-jspsych",
        "file_type": "js",
        "order": 2,
    },
    {
        "name": "CHS Templates",
        "url": "https://unpkg.com/@lookit/templates@3.2.0",
        "integrity": "sha384-VOuebjugj2OrWh+NLn28VpM+bfSQNGw8HvEInoQgY9Fco2bchzUHXk9MAxCBMVW/",
        "category": "chs-jspsych",
        "file_type": "js",
        "order": 3,
    },
    {
        "name": "CHS Init jsPsych",
        "url": "https://unpkg.com/@lookit/lookit-initjspsych@3.2.0",
        "integrity": "sha384-e7tzYepJWL+2m2J5oXfaCtcgEXE0FmZngMY1mCsqdi+pAN3ouqkqnrmxmFb+KE5z",
        "category": "chs-jspsych",
        "file_type": "js",
        "order": 4,
    },
    {
        "name": "CHS Record",
        "url": "https://unpkg.com/@lookit/record@7.0.0",
        "integrity": "sha384-J6UlRs78jVMqxRk7qup5sX7lSaJnmmPGeiJ0Zi4KYPKlEG0Vx72iooB7N5eFbKgG",
        "category": "chs-jspsych",
        "file_type": "js",
        "order": 5,
    },
    {
        "name": "CHS Surveys",
        "url": "https://unpkg.com/@lookit/surveys@7.0.0",
        "integrity": "sha384-swscT+LLjYy4Od2kzdxf1NgDEx8+fjOa0p04Vor3XNpvhn2bWUN7/zpO9qE+DCLI",
        "category": "chs-jspsych",
        "file_type": "js",
        "order": 6,
    },
]


def seed_auto_load_plugins(apps, schema_editor):
    JSPsychPlugin = apps.get_model("studies", "JSPsychPlugin")
    for data in JSPSYCH_LIBRARY + CHS_JSPSYCH_PLUGINS:
        JSPsychPlugin.objects.create(**data)


class Migration(migrations.Migration):
    dependencies = [
        ("studies", "0108_add_jspsych_plugin_model"),
    ]

    operations = [
        migrations.AddField(
            model_name="jspsychplugin",
            name="order",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="jspsychplugin",
            name="file_type",
            field=models.CharField(
                choices=[("js", "JavaScript"), ("css", "CSS")],
                default="js",
                max_length=3,
            ),
        ),
        migrations.RunPython(seed_auto_load_plugins, migrations.RunPython.noop),
    ]

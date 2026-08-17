from django.db import migrations

# Tangram Game plugin: pin the previously-unpinned unpkg URL to a specific version.
# Without a pinned version, a future package release would make unpkg serve a file
# whose hash no longer matches the fixed integrity attribute.
TANGRAM_NAME = "Tangram Game"
TANGRAM_URL_UNPINNED = "https://unpkg.com/@jspsych-contrib/plugin-tangram-game"
TANGRAM_URL_PINNED = "https://unpkg.com/@jspsych-contrib/plugin-tangram-game@1.0.0"


def drop_autoload_plugins_from_studies(apps, schema_editor):
    """Remove autoload plugins from every study's jspsych_plugins m2m.

    Migration 0108 seeded existing jsPsych studies with the full core+contrib
    plugin list, which includes the autoload plugins. But autoload plugins are
    loaded globally on the study page (via the autoload_plugins / jspsych_library
    / chs_plugins context querysets), not per-study, so having them in a study's
    m2m makes the template load them twice.

    JSPsychForm.save() already treats the m2m as "non-autoload, explicitly-selected
    plugins only" (it .set()s only the selectable, autoload=False fields), so any
    study re-saved through the form self-heals. This migration applies the same
    cleanup to all existing studies at once instead of waiting for each to be edited.
    """
    study = apps.get_model("studies", "Study")

    for s in study.objects.filter(jspsych_plugins__autoload=True).distinct():
        s.jspsych_plugins.set(s.jspsych_plugins.filter(autoload=False))


def pin_tangram_plugin_version(apps, schema_editor):
    jspsych_plugin = apps.get_model("studies", "JSPsychPlugin")
    jspsych_plugin.objects.filter(name=TANGRAM_NAME, url=TANGRAM_URL_UNPINNED).update(
        url=TANGRAM_URL_PINNED
    )


def unpin_tangram_plugin_version(apps, schema_editor):
    jspsych_plugin = apps.get_model("studies", "JSPsychPlugin")
    jspsych_plugin.objects.filter(name=TANGRAM_NAME, url=TANGRAM_URL_PINNED).update(
        url=TANGRAM_URL_UNPINNED
    )


class Migration(migrations.Migration):
    """Two jsPsych plugin-loading fixes:

    1. Existing studies double-loaded their 5 autoload plugins (0108 attached them
       to each study's m2m but they should not be there - template loads them globally).
    2. The Tangram Game plugin used an unpinned unpkg URL with a fixed SRI hash,
       which would break loading on the next package release.
    """

    dependencies = [
        ("studies", "0108_add_jspsych_plugin_model"),
    ]

    operations = [
        migrations.RunPython(
            drop_autoload_plugins_from_studies,
            migrations.RunPython.noop,
        ),
        migrations.RunPython(
            pin_tangram_plugin_version,
            unpin_tangram_plugin_version,
        ),
    ]
